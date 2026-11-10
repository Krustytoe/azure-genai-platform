import pytest
from fastapi.testclient import TestClient

from ragapi.main import create_app
from ragapi.pipeline import RagPipeline
from ragapi.providers.base import Completion, ProviderError, ProviderThrottledError
from ragapi.providers.fake import FakeChatModel, FakeRetriever

from .conftest import CORPUS, StubModel, StubRetriever


@pytest.fixture
def client(settings, harness) -> TestClient:
    pipeline = RagPipeline(FakeRetriever(CORPUS), FakeChatModel(), settings, harness.telemetry)
    return TestClient(create_app(settings, pipeline))


def test_healthz(client) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_chat_returns_grounded_answer(client) -> None:
    r = client.post(
        "/v1/chat",
        json={"question": "What is the domestic meal per diem?"},
        headers={"x-tenant-id": "finance", "x-request-id": "abc123"},
    )
    body = r.json()
    assert r.status_code == 200
    assert r.headers["x-request-id"] == "abc123"
    assert body["request_id"] == "abc123"
    assert body["grounded"] is True
    assert "$75" in body["answer"]
    assert body["citations"][0]["source"] == "travel-and-expense-policy.md"
    assert body["usage"]["input_tokens"] > 0


def test_off_topic_question_is_refused(client) -> None:
    body = client.post("/v1/chat", json={"question": "Who painted the Mona Lisa?"}).json()
    assert body["grounded"] is False
    assert body["usage"] is None


def test_pii_never_echoed(client) -> None:
    body = client.post(
        "/v1/chat", json={"question": "I'm 123-45-6789, how many PTO days carry over?"}
    ).json()
    assert "123-45-6789" not in str(body)
    assert body["redactions"] == {"ssn": 1}


@pytest.mark.parametrize("tenant", ["Finance", "a" * 64, "bad tenant", "-x"])
def test_rejects_bad_tenant_ids(client, tenant) -> None:
    r = client.post("/v1/chat", json={"question": "hi"}, headers={"x-tenant-id": tenant})
    assert r.status_code == 422


@pytest.mark.parametrize("question", ["", "   "])
def test_rejects_blank_questions(client, question) -> None:
    assert client.post("/v1/chat", json={"question": question}).status_code == 422


def test_rejects_oversized_questions(client, settings) -> None:
    r = client.post("/v1/chat", json={"question": "x" * (settings.max_question_chars + 1)})
    assert r.status_code == 422


@pytest.mark.parametrize(
    ("error", "status"), [(ProviderThrottledError("slow"), 429), (ProviderError("down"), 502)]
)
def test_upstream_errors_map_to_http(settings, harness, passages, error, status) -> None:
    class Failing(StubModel):
        def generate(self, **kwargs):
            raise error

    pipeline = RagPipeline(
        StubRetriever(passages), Failing(Completion("", 0, 0)), settings, harness.telemetry
    )
    r = TestClient(create_app(settings, pipeline)).post("/v1/chat", json={"question": "per diem"})
    assert r.status_code == status
    assert "down" not in r.text  # internal detail is not leaked
    if status == 429:
        assert r.headers["retry-after"] == "5"


def test_factory_builds_fake_provider_from_settings(settings) -> None:
    r = TestClient(create_app(settings)).post(
        "/v1/chat", json={"question": "Sev1 acknowledge page"}
    )
    assert r.status_code == 200
