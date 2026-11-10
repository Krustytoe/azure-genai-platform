"""The RAG request path: redact -> retrieve -> gate -> generate -> cite -> account."""

import re
import time
from collections import Counter
from dataclasses import dataclass, field

from opentelemetry.trace import Status, StatusCode

from .config import Settings
from .prompts import REFUSAL, SYSTEM_PROMPT, build_context
from .providers.base import ChatModel, Completion, Passage, Retriever
from .redaction import redact
from .telemetry import Telemetry

_CITATION = re.compile(r"\[(\d{1,2})\]")
_SNIPPET_CHARS = 240


@dataclass(frozen=True)
class Citation:
    id: int
    source: str
    score: float
    snippet: str


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


@dataclass
class Answer:
    answer: str
    grounded: bool
    blocked: bool = False
    citations: list[Citation] = field(default_factory=list)
    usage: Usage | None = None
    redactions: dict[str, int] = field(default_factory=dict)
    outcome: str = "answered"


class RagPipeline:
    def __init__(
        self,
        retriever: Retriever,
        model: ChatModel,
        settings: Settings,
        telemetry: Telemetry | None = None,
    ) -> None:
        self._retriever = retriever
        self._model = model
        self._settings = settings
        self._telemetry = telemetry or Telemetry()

    def ask(self, question: str, tenant: str = "default") -> Answer:
        t = self._telemetry
        attrs = {"tenant": tenant}

        with t.tracer.start_as_current_span("rag.ask", attributes=attrs) as span:
            try:
                answer = self._ask(question, tenant)
            except Exception as exc:
                span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
                t.requests.add(1, {**attrs, "outcome": "error"})
                raise
            span.set_attribute("rag.outcome", answer.outcome)
            span.set_attribute("rag.grounded", answer.grounded)
            t.requests.add(1, {**attrs, "outcome": answer.outcome})
            return answer

    def _ask(self, question: str, tenant: str) -> Answer:
        s, t = self._settings, self._telemetry
        redactions: Counter[str] = Counter()

        if s.redact_pii:
            result = redact(question)
            question = result.text
            redactions.update(result.counts)
            for label, n in result.counts.items():
                t.redactions.add(n, {"tenant": tenant, "type": label, "direction": "input"})

        with t.tracer.start_as_current_span("rag.retrieve") as rspan:
            passages = self._retriever.retrieve(question, s.top_k)
            relevant = [p for p in passages if p.score >= s.min_score]
            rspan.set_attribute("rag.retrieved", len(passages))
            rspan.set_attribute("rag.relevant", len(relevant))

        # No evidence, no model call: cheaper, and the model can't hallucinate.
        if not relevant:
            return Answer(
                answer=REFUSAL, grounded=False, redactions=dict(redactions), outcome="no_context"
            )

        completion = self._generate(question, relevant, tenant)

        text = completion.text
        if s.redact_pii:
            result = redact(text)
            text = result.text
            redactions.update(result.counts)
            for label, n in result.counts.items():
                t.redactions.add(n, {"tenant": tenant, "type": label, "direction": "output"})

        usage = self._account(completion.input_tokens, completion.output_tokens, tenant)

        if completion.blocked:
            return Answer(
                answer=text,
                grounded=False,
                blocked=True,
                usage=usage,
                redactions=dict(redactions),
                outcome="blocked",
            )

        citations = _citations(text, relevant)
        refused = REFUSAL in text
        return Answer(
            answer=text,
            grounded=bool(citations) and not refused,
            citations=citations,
            usage=usage,
            redactions=dict(redactions),
            outcome="no_context" if refused else "answered",
        )

    def _generate(self, question: str, passages: list[Passage], tenant: str) -> Completion:
        s, t, m = self._settings, self._telemetry, self._model
        span_attrs = {
            "gen_ai.operation.name": "chat",
            "gen_ai.system": m.system,
            "gen_ai.request.model": m.model_id,
            "gen_ai.request.max_tokens": s.max_output_tokens,
            "gen_ai.request.temperature": s.temperature,
        }
        with t.tracer.start_as_current_span(f"chat {m.model_id}", attributes=span_attrs) as gspan:
            start = time.perf_counter()
            completion = m.generate(
                system_prompt=SYSTEM_PROMPT,
                context=build_context(passages),
                question=question,
                max_tokens=s.max_output_tokens,
                temperature=s.temperature,
            )
            gspan.set_attribute("gen_ai.usage.input_tokens", completion.input_tokens)
            gspan.set_attribute("gen_ai.usage.output_tokens", completion.output_tokens)
            gspan.set_attribute("rag.guardrail.blocked", completion.blocked)
            gspan.set_attribute("rag.latency_ms", round((time.perf_counter() - start) * 1000, 1))

        base = {"gen_ai.system": m.system, "gen_ai.request.model": m.model_id, "tenant": tenant}
        t.token_usage.record(completion.input_tokens, {**base, "gen_ai.token.type": "input"})
        t.token_usage.record(completion.output_tokens, {**base, "gen_ai.token.type": "output"})
        return completion

    def _account(self, input_tokens: int, output_tokens: int, tenant: str) -> Usage:
        s = self._settings
        cost = (input_tokens / 1000) * s.price_input_per_1k + (
            output_tokens / 1000
        ) * s.price_output_per_1k
        attrs = {"tenant": tenant, "gen_ai.request.model": self._model.model_id}
        self._telemetry.cost.add(cost, attrs)
        return Usage(input_tokens, output_tokens, round(cost, 6))


def _citations(text: str, passages: list[Passage]) -> list[Citation]:
    seen: list[int] = []
    for match in _CITATION.finditer(text):
        n = int(match.group(1))
        if 1 <= n <= len(passages) and n not in seen:
            seen.append(n)
    return [
        Citation(
            id=n,
            source=passages[n - 1].source,
            score=round(passages[n - 1].score, 4),
            snippet=passages[n - 1].text.strip()[:_SNIPPET_CHARS],
        )
        for n in seen
    ]
