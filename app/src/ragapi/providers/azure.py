"""Azure adapters: AI Search (hybrid + semantic ranking) and Azure OpenAI chat."""

from collections.abc import Callable
from typing import Any

import httpx
import openai
from openai import AzureOpenAI

from .base import Completion, Passage, ProviderError, ProviderThrottledError

TokenProvider = Callable[[], str]

BLOCKED_MESSAGE = "Sorry, I can't help with that request."
_THROTTLE_STATUS = frozenset({429, 503})
# Semantic reranker scores run 0-4; normalise to the pipeline's 0-1 scale.
_RERANKER_MAX = 4.0
# Candidates handed to the semantic reranker (it reorders the top 50).
_SEMANTIC_CANDIDATES = 50


class AzureAISearchRetriever:
    def __init__(
        self,
        endpoint: str,
        index: str,
        token_provider: TokenProvider,
        semantic_config: str | None = "default",
        api_version: str = "2024-07-01",
        vector_field: str = "contentVector",
        http: httpx.Client | None = None,
    ) -> None:
        self._url = f"{endpoint.rstrip('/')}/indexes/{index}/docs/search"
        self._token = token_provider
        self._semantic = semantic_config
        self._api_version = api_version
        self._vector_field = vector_field
        self._http = http or httpx.Client(timeout=10.0)

    def retrieve(self, query: str, top_k: int) -> list[Passage]:
        # The index's vectorizer embeds the query server-side, with the search
        # service's own identity, so the app never handles embeddings.
        body: dict[str, Any] = {
            "top": top_k,
            "select": "content,source",
            "vectorQueries": [
                {
                    "kind": "text",
                    "text": query,
                    "fields": self._vector_field,
                    "k": _SEMANTIC_CANDIDATES if self._semantic else top_k,
                }
            ],
        }
        if self._semantic:
            body |= {
                "search": query,
                "queryType": "semantic",
                "semanticConfiguration": self._semantic,
            }

        try:
            response = self._http.post(
                self._url,
                params={"api-version": self._api_version},
                json=body,
                headers={"Authorization": f"Bearer {self._token()}"},
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"search failed: {type(exc).__name__}") from exc

        if response.status_code in _THROTTLE_STATUS:
            raise ProviderThrottledError(f"search throttled: HTTP {response.status_code}")
        if response.is_error:
            raise ProviderError(f"search failed: HTTP {response.status_code}")

        passages = []
        for doc in response.json().get("value", []):
            if self._semantic:
                score = min(float(doc.get("@search.rerankerScore") or 0.0) / _RERANKER_MAX, 1.0)
            else:
                score = float(doc.get("@search.score", 0.0))
            if doc.get("content"):
                passages.append(
                    Passage(text=doc["content"], source=doc.get("source", "unknown"), score=score)
                )
        return passages


class AzureOpenAIChatModel:
    system = "az.ai.openai"

    def __init__(
        self,
        endpoint: str,
        deployment: str,
        api_version: str = "2024-10-21",
        token_provider: TokenProvider | None = None,
        api_key: str | None = None,
        client: AzureOpenAI | None = None,
    ) -> None:
        self.model_id = deployment
        if client is None:
            auth: dict[str, Any] = (
                {"api_key": api_key} if api_key else {"azure_ad_token_provider": token_provider}
            )
            client = AzureOpenAI(
                azure_endpoint=endpoint, api_version=api_version, max_retries=2, timeout=60, **auth
            )
        self._client = client

    def generate(
        self,
        *,
        system_prompt: str,
        context: str,
        question: str,
        max_tokens: int,
        temperature: float,
    ) -> Completion:
        try:
            response = self._client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"{context}\n\nQuestion: {question}"},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except openai.RateLimitError as exc:
            raise ProviderThrottledError("azure openai throttled: HTTP 429") from exc
        except openai.BadRequestError as exc:
            # The content filter rejected the prompt (harm category or Prompt Shields).
            if exc.code == "content_filter":
                return Completion(
                    text=BLOCKED_MESSAGE, input_tokens=0, output_tokens=0, blocked=True
                )
            raise ProviderError(f"azure openai failed: HTTP {exc.status_code}") from exc
        except openai.APIStatusError as exc:
            raise ProviderError(f"azure openai failed: HTTP {exc.status_code}") from exc
        except openai.APIError as exc:
            raise ProviderError(f"azure openai failed: {type(exc).__name__}") from exc

        choice = response.choices[0]
        blocked = choice.finish_reason == "content_filter"
        text = (choice.message.content or "").strip() or (BLOCKED_MESSAGE if blocked else "")
        usage = response.usage
        return Completion(
            text=text,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            blocked=blocked,
        )
