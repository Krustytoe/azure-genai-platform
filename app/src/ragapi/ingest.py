"""Build the AI Search index from a folder of Markdown documents.

    uv run python -m ragapi.ingest ../evals/corpus

Creates or updates the index (fields, HNSW vector profile, an Azure OpenAI
vectorizer so queries are embedded server-side, and a semantic configuration),
then chunks, embeds and upserts the documents. Re-running is idempotent:
document IDs are derived from file name and chunk position.

Runs as the ingestion identity (Search Index Data Contributor + Search Service
Contributor + Cognitive Services OpenAI User), from a network that can reach
both private endpoints.
"""

import argparse
import base64
import hashlib
import logging
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import httpx

from .chunking import Chunk, chunk_corpus
from .config import Settings

log = logging.getLogger("ragapi.ingest")

EmbedFn = Callable[[Sequence[str]], list[list[float]]]
_EMBED_BATCH = 16
_UPLOAD_BATCH = 100


def document_id(chunk: Chunk) -> str:
    digest = hashlib.sha256(f"{chunk.source}#{chunk.index}".encode()).digest()
    return base64.urlsafe_b64encode(digest[:18]).decode()  # key-safe, 24 chars


def index_definition(settings: Settings) -> dict[str, Any]:
    if not settings.azure_openai_resource_uri:
        raise ValueError("RAG_AZURE_OPENAI_RESOURCE_URI is required to configure the vectorizer")
    return {
        "name": settings.azure_search_index,
        "fields": [
            {"name": "id", "type": "Edm.String", "key": True, "filterable": True},
            {"name": "content", "type": "Edm.String", "searchable": True},
            {"name": "source", "type": "Edm.String", "filterable": True, "facetable": True},
            {
                "name": "contentVector",
                "type": "Collection(Edm.Single)",
                "searchable": True,
                "retrievable": False,
                "stored": False,
                "dimensions": settings.azure_embedding_dimensions,
                "vectorSearchProfile": "default",
            },
        ],
        "vectorSearch": {
            "algorithms": [
                {"name": "hnsw", "kind": "hnsw", "hnswParameters": {"metric": "cosine"}}
            ],
            "vectorizers": [
                {
                    "name": "aoai",
                    "kind": "azureOpenAI",
                    # No apiKey: the search service authenticates with its managed identity.
                    "azureOpenAIParameters": {
                        "resourceUri": settings.azure_openai_resource_uri.rstrip("/"),
                        "deploymentId": settings.azure_embedding_deployment,
                        "modelName": settings.azure_embedding_model,
                    },
                }
            ],
            "profiles": [{"name": "default", "algorithm": "hnsw", "vectorizer": "aoai"}],
        },
        "semantic": {
            "configurations": [
                {
                    "name": settings.azure_search_semantic_config or "default",
                    "prioritizedFields": {"prioritizedContentFields": [{"fieldName": "content"}]},
                }
            ]
        },
    }


class SearchIndexClient:
    def __init__(self, settings: Settings, token: Callable[[], str], http: httpx.Client) -> None:
        if not settings.azure_search_endpoint:
            raise ValueError("RAG_AZURE_SEARCH_ENDPOINT is required")
        self._base = settings.azure_search_endpoint.rstrip("/")
        self._index = settings.azure_search_index
        self._params = {"api-version": settings.azure_search_api_version}
        self._token = token
        self._http = http

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token()}"}

    def put_index(self, definition: dict[str, Any]) -> None:
        r = self._http.put(
            f"{self._base}/indexes/{self._index}",
            params=self._params,
            json=definition,
            headers=self._headers(),
        )
        r.raise_for_status()

    def upload(self, docs: list[dict[str, Any]]) -> int:
        r = self._http.post(
            f"{self._base}/indexes/{self._index}/docs/index",
            params=self._params,
            json={"value": docs},
            headers=self._headers(),
        )
        r.raise_for_status()
        failed = [d for d in r.json().get("value", []) if not d.get("status")]
        if failed:
            raise RuntimeError(f"{len(failed)} documents failed to index: {failed[:3]}")
        return len(docs)


def ingest(corpus_dir: Path, settings: Settings, index: SearchIndexClient, embed: EmbedFn) -> int:
    chunks = chunk_corpus(corpus_dir)
    if not chunks:
        raise ValueError(f"no Markdown content found in {corpus_dir}")

    index.put_index(index_definition(settings))
    log.info("index %s ready; embedding %d chunks", settings.azure_search_index, len(chunks))

    docs: list[dict[str, Any]] = []
    for start in range(0, len(chunks), _EMBED_BATCH):
        batch = chunks[start : start + _EMBED_BATCH]
        vectors = embed([c.text for c in batch])
        docs.extend(
            {
                "@search.action": "mergeOrUpload",
                "id": document_id(c),
                "content": c.text,
                "source": c.source,
                "contentVector": v,
            }
            for c, v in zip(batch, vectors, strict=True)
        )

    uploaded = sum(
        index.upload(docs[i : i + _UPLOAD_BATCH]) for i in range(0, len(docs), _UPLOAD_BATCH)
    )
    log.info("uploaded %d chunks from %s", uploaded, corpus_dir)
    return uploaded


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - thin CLI wiring
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("corpus_dir", type=Path)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from azure.identity import (
        AzureAuthorityHosts,
        DefaultAzureCredential,
        get_bearer_token_provider,
    )
    from openai import AzureOpenAI

    from .config import AzureCloud

    settings = Settings()
    authority = (
        AzureAuthorityHosts.AZURE_GOVERNMENT
        if settings.azure_cloud is AzureCloud.USGOVERNMENT
        else AzureAuthorityHosts.AZURE_PUBLIC_CLOUD
    )
    credential = DefaultAzureCredential(authority=authority)
    if not settings.azure_openai_resource_uri:
        parser.error("set RAG_AZURE_OPENAI_RESOURCE_URI")

    aoai = AzureOpenAI(
        azure_endpoint=settings.azure_openai_resource_uri,
        api_version=settings.azure_openai_api_version,
        azure_ad_token_provider=get_bearer_token_provider(credential, settings.openai_scope),
    )

    def embed(texts: Sequence[str]) -> list[list[float]]:
        response = aoai.embeddings.create(
            model=settings.azure_embedding_deployment,
            input=list(texts),
            dimensions=settings.azure_embedding_dimensions,
        )
        return [d.embedding for d in sorted(response.data, key=lambda d: d.index)]

    with httpx.Client(timeout=60.0) as http:
        index = SearchIndexClient(
            settings, get_bearer_token_provider(credential, settings.search_scope), http
        )
        ingest(args.corpus_dir, settings, index, embed)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
