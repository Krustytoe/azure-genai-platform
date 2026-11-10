from ragapi.config import Settings
from ragapi.providers import build_providers
from ragapi.providers.azure import AzureAISearchRetriever, AzureOpenAIChatModel
from ragapi.providers.fake import FakeChatModel, FakeRetriever

from .conftest import CORPUS


def azure_settings(**overrides) -> Settings:
    return Settings(
        provider="azure",
        azure_openai_endpoint="https://larkspur-apim.azure-api.us/",
        azure_search_endpoint="https://larkspur-search.search.azure.us",
        azure_cloud="usgovernment",
        **overrides,
    )


def test_builds_azure_adapters_with_entra_auth() -> None:
    # Constructing the credential and token providers makes no network calls.
    retriever, model = build_providers(azure_settings())
    assert isinstance(retriever, AzureAISearchRetriever)
    assert isinstance(model, AzureOpenAIChatModel)
    assert model.model_id == "chat"


def test_builds_azure_adapters_with_gateway_key() -> None:
    _, model = build_providers(azure_settings(azure_openai_api_key="sub-key"))
    assert model._client.api_key == "sub-key"


def test_builds_fake_adapters() -> None:
    retriever, model = build_providers(Settings(fake_corpus_dir=CORPUS))
    assert isinstance(retriever, FakeRetriever)
    assert isinstance(model, FakeChatModel)
