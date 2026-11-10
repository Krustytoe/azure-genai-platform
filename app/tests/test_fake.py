import pytest

from ragapi.pipeline import RagPipeline
from ragapi.providers.fake import FakeChatModel, FakeRetriever

from .conftest import CORPUS


@pytest.fixture(scope="module")
def retriever() -> FakeRetriever:
    return FakeRetriever(CORPUS)


def test_retrieves_the_right_document(retriever) -> None:
    top = retriever.retrieve("What is the domestic meal per diem?", 3)[0]
    assert top.source == "travel-and-expense-policy.md"
    assert "$75" in top.text
    assert 0 < top.score <= 1


def test_off_topic_query_scores_low(retriever) -> None:
    hits = retriever.retrieve("Who painted the Mona Lisa?", 3)
    assert all(p.score < 0.35 for p in hits)


def test_stopword_only_query_returns_nothing(retriever) -> None:
    assert retriever.retrieve("what is the", 3) == []


def test_empty_corpus_is_rejected(tmp_path) -> None:
    with pytest.raises(ValueError, match="no Markdown"):
        FakeRetriever(tmp_path)


def test_end_to_end_offline(retriever, settings, harness) -> None:
    pipeline = RagPipeline(retriever, FakeChatModel(), settings, harness.telemetry)
    answer = pipeline.ask("How many PTO days carry over into the next year?")
    assert answer.grounded
    assert answer.citations[0].source == "paid-time-off-policy.md"
