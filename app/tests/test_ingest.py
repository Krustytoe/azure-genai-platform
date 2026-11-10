import json

import httpx
import pytest

from ragapi.chunking import Chunk
from ragapi.config import Settings
from ragapi.ingest import SearchIndexClient, document_id, index_definition, ingest

from .conftest import CORPUS


@pytest.fixture
def azure_settings() -> Settings:
    return Settings(
        azure_search_endpoint="https://larkspur-search.search.windows.net/",
        azure_openai_resource_uri="https://larkspur-aoai.openai.azure.com/",
        azure_embedding_dimensions=256,
    )


def test_index_definition_is_keyless_and_vectorized(azure_settings) -> None:
    d = index_definition(azure_settings)
    vector = next(f for f in d["fields"] if f["name"] == "contentVector")
    assert vector["dimensions"] == 256
    vectorizer = d["vectorSearch"]["vectorizers"][0]
    assert (
        vectorizer["azureOpenAIParameters"]["resourceUri"]
        == "https://larkspur-aoai.openai.azure.com"
    )
    assert "apiKey" not in vectorizer["azureOpenAIParameters"]  # managed identity
    assert d["semantic"]["configurations"][0]["name"] == "default"


def test_index_definition_requires_resource_uri() -> None:
    with pytest.raises(ValueError, match="RESOURCE_URI"):
        index_definition(Settings())


def test_document_ids_are_stable_and_key_safe() -> None:
    a = document_id(Chunk("x", "travel.md", 3))
    assert a == document_id(Chunk("different text", "travel.md", 3))
    assert a != document_id(Chunk("x", "travel.md", 4))
    assert len(a) == 24
    assert "/" not in a
    assert "+" not in a


def test_ingest_creates_index_then_uploads_embedded_chunks(azure_settings) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append((request.method, request.url.path, body))
        if request.method == "POST":
            return httpx.Response(
                200, json={"value": [{"key": d["id"], "status": True} for d in body["value"]]}
            )
        return httpx.Response(201, json=body)

    embedded = []

    def embed(texts):
        embedded.extend(texts)
        return [[0.1] * 256 for _ in texts]

    client = SearchIndexClient(
        azure_settings, lambda: "tok", httpx.Client(transport=httpx.MockTransport(handler))
    )
    uploaded = ingest(CORPUS, azure_settings, client, embed)

    assert calls[0][:2] == ("PUT", "/indexes/handbook")
    uploads = [c for c in calls if c[0] == "POST"]
    assert uploads[0][1] == "/indexes/handbook/docs/index"
    docs = [d for _, _, body in uploads for d in body["value"]]
    assert uploaded == len(docs) == len(embedded) > 10
    assert {d["@search.action"] for d in docs} == {"mergeOrUpload"}
    assert any("$75 per day" in d["content"] for d in docs)


def test_ingest_surfaces_failed_documents(azure_settings) -> None:
    def handler(request):
        if request.method == "POST":
            return httpx.Response(
                200, json={"value": [{"key": "x", "status": False, "errorMessage": "bad"}]}
            )
        return httpx.Response(201, json={})

    client = SearchIndexClient(
        azure_settings, lambda: "tok", httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(RuntimeError, match="failed to index"):
        ingest(CORPUS, azure_settings, client, lambda texts: [[0.0] * 256 for _ in texts])


def test_ingest_rejects_empty_corpus(azure_settings, tmp_path) -> None:
    client = SearchIndexClient(
        azure_settings,
        lambda: "tok",
        httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))),
    )
    with pytest.raises(ValueError, match="no Markdown"):
        ingest(tmp_path, azure_settings, client, lambda t: [])


def test_index_client_requires_endpoint() -> None:
    with pytest.raises(ValueError, match="SEARCH_ENDPOINT"):
        SearchIndexClient(Settings(), lambda: "t", httpx.Client())
