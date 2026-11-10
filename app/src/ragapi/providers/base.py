"""Provider-neutral interfaces. The pipeline only ever talks to these."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Passage:
    text: str
    source: str
    score: float  # normalised to 0..1, higher is more relevant


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    blocked: bool = False  # a provider-side guardrail intervened


class ProviderError(RuntimeError):
    """The upstream model or retrieval service failed."""


class ProviderThrottledError(ProviderError):
    """The upstream service is rate limiting us; the caller should back off."""


class Retriever(Protocol):
    def retrieve(self, query: str, top_k: int) -> list[Passage]: ...


class ChatModel(Protocol):
    system: str  # OpenTelemetry gen_ai.system value, e.g. "aws.bedrock"
    model_id: str

    def generate(
        self,
        *,
        system_prompt: str,
        context: str,
        question: str,
        max_tokens: int,
        temperature: float,
    ) -> Completion: ...
