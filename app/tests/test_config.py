import pytest
from pydantic import ValidationError

from ragapi.config import AzureCloud, Provider, Settings


def test_defaults_to_fake(monkeypatch) -> None:
    monkeypatch.delenv("RAG_PROVIDER", raising=False)
    assert Settings().provider is Provider.FAKE


def test_azure_requires_endpoints() -> None:
    with pytest.raises(
        ValidationError, match="RAG_AZURE_OPENAI_ENDPOINT, RAG_AZURE_SEARCH_ENDPOINT"
    ):
        Settings(provider="azure")


def test_government_cloud_scopes() -> None:
    s = Settings(azure_cloud="usgovernment")
    assert s.azure_cloud is AzureCloud.USGOVERNMENT
    assert s.openai_scope == "https://cognitiveservices.azure.us/.default"
    assert s.search_scope == "https://search.azure.us/.default"


def test_public_cloud_scopes() -> None:
    s = Settings()
    assert s.openai_scope == "https://cognitiveservices.azure.com/.default"
    assert s.search_scope == "https://search.azure.com/.default"


def test_reads_environment_and_keeps_key_secret(monkeypatch) -> None:
    monkeypatch.setenv("RAG_PROVIDER", "azure")
    monkeypatch.setenv("RAG_AZURE_OPENAI_ENDPOINT", "https://gw.example.com/")
    monkeypatch.setenv("RAG_AZURE_SEARCH_ENDPOINT", "https://search.example.com")
    monkeypatch.setenv("RAG_AZURE_OPENAI_API_KEY", "sub-key-123")
    monkeypatch.setenv("RAG_AZURE_SEARCH_SEMANTIC_CONFIG", "")
    s = Settings()
    assert s.provider is Provider.AZURE
    assert s.azure_search_semantic_config is None
    assert "sub-key-123" not in repr(s)
    assert s.azure_openai_api_key.get_secret_value() == "sub-key-123"


def test_rejects_out_of_range_values() -> None:
    with pytest.raises(ValidationError):
        Settings(min_score=1.5)
