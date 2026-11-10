"""Azure adapters against mock transports: real SDK request/response handling, no network."""

import json

import httpx
import pytest
from openai import AzureOpenAI

from ragapi.providers.azure import BLOCKED_MESSAGE, AzureAISearchRetriever, AzureOpenAIChatModel
from ragapi.providers.base import ProviderError, ProviderThrottledError


def search_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def retriever(handler, semantic="default") -> AzureAISearchRetriever:
    return AzureAISearchRetriever(
        "https://larkspur-search.search.azure.us/",
        "handbook",
        token_provider=lambda: "tok",
        semantic_config=semantic,
        http=search_client(handler),
    )


def test_hybrid_semantic_query_and_score_normalisation() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "value": [
                    {
                        "content": "Per diem is $75.",
                        "source": "travel.md",
                        "@search.score": 0.03,
                        "@search.rerankerScore": 3.2,
                    },
                    {
                        "content": "Hotel cap.",
                        "source": "travel.md",
                        "@search.score": 0.02,
                        "@search.rerankerScore": 1.0,
                    },
                    {"content": "", "source": "empty.md", "@search.rerankerScore": 2.0},
                ]
            },
        )

    passages = retriever(handler).retrieve("per diem", 3)

    assert seen["url"] == (
        "https://larkspur-search.search.azure.us/indexes/handbook/docs/search?api-version=2024-07-01"
    )
    assert seen["auth"] == "Bearer tok"
    body = seen["body"]
    assert body["queryType"] == "semantic"
    assert body["semanticConfiguration"] == "default"
    assert body["search"] == "per diem"
    assert body["vectorQueries"][0] == {
        "kind": "text",
        "text": "per diem",
        "fields": "contentVector",
        "k": 50,
    }
    assert [round(p.score, 2) for p in passages] == [0.8, 0.25]  # reranker / 4, empty doc dropped


def test_vector_only_uses_search_score() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "queryType" not in body
        assert "search" not in body
        assert body["vectorQueries"][0]["k"] == 2
        return httpx.Response(
            200, json={"value": [{"content": "x", "source": "a.md", "@search.score": 0.91}]}
        )

    assert retriever(handler, semantic=None).retrieve("q", 2)[0].score == pytest.approx(0.91)


@pytest.mark.parametrize(
    ("status", "exc"),
    [(429, ProviderThrottledError), (503, ProviderThrottledError), (403, ProviderError)],
)
def test_search_http_errors(status, exc) -> None:
    with pytest.raises(exc, match=str(status)):
        retriever(lambda r: httpx.Response(status)).retrieve("q", 1)


def test_search_transport_errors() -> None:
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(ProviderError, match="ConnectError"):
        retriever(handler).retrieve("q", 1)


# --- Azure OpenAI ---------------------------------------------------------


def chat_model(handler) -> AzureOpenAIChatModel:
    client = AzureOpenAI(
        azure_endpoint="https://larkspur-apim.azure-api.us/",
        api_version="2024-10-21",
        api_key="subscription-key",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return AzureOpenAIChatModel("https://unused/", "chat", client=client)


def completion(content, finish_reason="stop", prompt=900, completion_tokens=12) -> dict:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-4.1-mini",
        "choices": [
            {
                "index": 0,
                "finish_reason": finish_reason,
                "message": {"role": "assistant", "content": content},
            }
        ],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt + completion_tokens,
        },
    }


def generate(model):
    return model.generate(
        system_prompt="SYS", context="CTX", question="Q?", max_tokens=100, temperature=0.1
    )


def test_chat_request_shape_and_usage() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["key"] = request.headers.get("api-key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=completion(" $75 [1] "))

    result = generate(chat_model(handler))

    assert seen["path"] == "/openai/deployments/chat/chat/completions"
    assert (
        seen["key"] == "subscription-key"
    )  # APIM subscription key, sent the way the gateway expects
    assert seen["body"]["messages"][0] == {"role": "system", "content": "SYS"}
    assert seen["body"]["messages"][1]["content"] == "CTX\n\nQuestion: Q?"
    assert seen["body"]["max_tokens"] == 100
    assert (result.text, result.input_tokens, result.output_tokens, result.blocked) == (
        "$75 [1]",
        900,
        12,
        False,
    )


def test_filtered_completion_is_blocked() -> None:
    result = generate(
        chat_model(lambda r: httpx.Response(200, json=completion(None, "content_filter")))
    )
    assert result.blocked
    assert result.text == BLOCKED_MESSAGE


def test_filtered_prompt_is_blocked_not_an_error() -> None:
    def handler(request):
        return httpx.Response(
            400,
            json={
                "error": {
                    "code": "content_filter",
                    "message": "The prompt was filtered.",
                    "param": "prompt",
                    "type": None,
                }
            },
        )

    result = generate(chat_model(handler))
    assert result.blocked
    assert result.input_tokens == 0


@pytest.mark.parametrize(
    ("status", "body", "exc"),
    [
        (429, {"error": {"code": "429", "message": "Rate limit"}}, ProviderThrottledError),
        (400, {"error": {"code": "invalid_request", "message": "bad"}}, ProviderError),
        (500, {"error": {"code": "server_error", "message": "boom"}}, ProviderError),
    ],
)
def test_chat_errors_are_translated(status, body, exc) -> None:
    with pytest.raises(exc):
        generate(chat_model(lambda r: httpx.Response(status, json=body)))


def test_chat_connection_errors() -> None:
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(ProviderError, match="APIConnectionError"):
        generate(chat_model(handler))


def test_builds_client_with_entra_token_provider() -> None:
    model = AzureOpenAIChatModel(
        "https://aoai.openai.azure.com/", "chat", token_provider=lambda: "tok"
    )
    assert model.model_id == "chat"
