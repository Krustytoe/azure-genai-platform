import pytest

from ragapi.pipeline import RagPipeline
from ragapi.prompts import REFUSAL
from ragapi.providers.base import Completion, ProviderError

from .conftest import StubModel, StubRetriever


def make(passages, completion, settings, harness):
    retriever = StubRetriever(passages)
    model = StubModel(completion)
    return RagPipeline(retriever, model, settings, harness.telemetry), retriever, model


def test_grounded_answer_with_citations(passages, settings, harness) -> None:
    pipeline, _, model = make(
        passages, Completion("Per diem is $75 per day [1].", 900, 20), settings, harness
    )
    answer = pipeline.ask("What is the meal per diem?", tenant="finance")

    assert answer.grounded
    assert answer.outcome == "answered"
    assert [c.id for c in answer.citations] == [1]
    assert answer.citations[0].source == "s3://docs/travel.md"
    # The low-scoring passage never reaches the model.
    assert "holidays" not in model.calls[0]["context"]


def test_no_relevant_context_skips_the_model(passages, settings, harness) -> None:
    low = [p for p in passages if p.score < settings.min_score]
    pipeline, _, model = make(low, Completion("unused", 1, 1), settings, harness)
    answer = pipeline.ask("Who won the world cup?")

    assert answer.answer == REFUSAL
    assert not answer.grounded
    assert answer.outcome == "no_context"
    assert model.calls == []
    assert answer.usage is None


def test_uncited_answer_is_not_grounded(passages, settings, harness) -> None:
    pipeline, _, _ = make(passages, Completion("It is $75.", 900, 5), settings, harness)
    assert not pipeline.ask("per diem?").grounded


def test_out_of_range_citations_are_dropped(passages, settings, harness) -> None:
    pipeline, _, _ = make(
        passages, Completion("See [7] and [2] and [2].", 900, 5), settings, harness
    )
    answer = pipeline.ask("hotel cap?")
    assert [c.id for c in answer.citations] == [2]


def test_model_refusal_is_reported_as_no_context(passages, settings, harness) -> None:
    pipeline, _, _ = make(passages, Completion(REFUSAL, 900, 30), settings, harness)
    answer = pipeline.ask("something adjacent")
    assert not answer.grounded
    assert answer.outcome == "no_context"


def test_guardrail_block_is_surfaced(passages, settings, harness) -> None:
    pipeline, _, _ = make(
        passages, Completion("Sorry, I can't help.", 900, 6, blocked=True), settings, harness
    )
    answer = pipeline.ask("per diem?")
    assert answer.blocked
    assert not answer.grounded
    assert answer.outcome == "blocked"


def test_pii_is_redacted_before_retrieval_and_generation(passages, settings, harness) -> None:
    pipeline, retriever, model = make(
        passages, Completion("Noted [1]. Email jane@example.com.", 900, 9), settings, harness
    )
    answer = pipeline.ask("My SSN is 123-45-6789, what is the per diem?")

    assert "123-45-6789" not in retriever.queries[0]
    assert "123-45-6789" not in model.calls[0]["question"]
    assert "jane@example.com" not in answer.answer
    assert answer.redactions == {"ssn": 1, "email": 1}


def test_redaction_can_be_disabled(passages, settings, harness) -> None:
    settings.redact_pii = False
    pipeline, retriever, _ = make(passages, Completion("ok [1]", 1, 1), settings, harness)
    pipeline.ask("ssn 123-45-6789")
    assert "123-45-6789" in retriever.queries[0]


def test_cost_and_tokens_are_attributed_to_tenant(passages, settings, harness) -> None:
    pipeline, _, _ = make(passages, Completion("ok [1]", 1000, 100), settings, harness)
    answer = pipeline.ask("per diem?", tenant="finance")

    expected = 1.0 * settings.price_input_per_1k + 0.1 * settings.price_output_per_1k
    assert answer.usage.estimated_cost_usd == pytest.approx(expected)

    cost = harness.metric_points("rag.cost")
    assert cost[0].attributes["tenant"] == "finance"
    assert cost[0].value == pytest.approx(expected)

    tokens = {
        p.attributes["gen_ai.token.type"]: p.sum
        for p in harness.metric_points("gen_ai.client.token.usage")
    }
    assert tokens == {"input": 1000, "output": 100}


def test_spans_follow_genai_conventions(passages, settings, harness) -> None:
    pipeline, _, _ = make(passages, Completion("ok [1]", 10, 2), settings, harness)
    pipeline.ask("per diem?")

    spans = {s.name: s for s in harness.spans.get_finished_spans()}
    chat = spans["chat stub-model"]
    assert chat.attributes["gen_ai.system"] == "stub"
    assert chat.attributes["gen_ai.usage.input_tokens"] == 10
    assert spans["rag.ask"].attributes["rag.outcome"] == "answered"
    assert spans["rag.retrieve"].attributes["rag.relevant"] == 2


def test_provider_errors_are_counted_and_reraised(passages, settings, harness) -> None:
    class Broken(StubModel):
        def generate(self, **kwargs):
            raise ProviderError("boom")

    pipeline = RagPipeline(StubRetriever(passages), Broken(None), settings, harness.telemetry)
    with pytest.raises(ProviderError):
        pipeline.ask("per diem?")

    outcomes = {p.attributes["outcome"]: p.value for p in harness.metric_points("rag.requests")}
    assert outcomes == {"error": 1}
