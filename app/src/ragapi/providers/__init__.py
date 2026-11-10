"""Provider wiring: pick adapters from settings."""

from ..config import Provider, Settings
from .base import ChatModel, Retriever


def build_providers(settings: Settings) -> tuple[Retriever, ChatModel]:
    if settings.provider is Provider.AZURE:
        from azure.identity import (
            AzureAuthorityHosts,
            DefaultAzureCredential,
            get_bearer_token_provider,
        )

        from ..config import AzureCloud
        from .azure import AzureAISearchRetriever, AzureOpenAIChatModel

        authority = (
            AzureAuthorityHosts.AZURE_GOVERNMENT
            if settings.azure_cloud is AzureCloud.USGOVERNMENT
            else AzureAuthorityHosts.AZURE_PUBLIC_CLOUD
        )
        credential = DefaultAzureCredential(authority=authority)
        assert settings.azure_openai_endpoint  # noqa: S101 - guaranteed by Settings validation
        assert settings.azure_search_endpoint  # noqa: S101
        api_key = settings.azure_openai_api_key
        return (
            AzureAISearchRetriever(
                settings.azure_search_endpoint,
                settings.azure_search_index,
                get_bearer_token_provider(credential, settings.search_scope),
                semantic_config=settings.azure_search_semantic_config,
                api_version=settings.azure_search_api_version,
            ),
            AzureOpenAIChatModel(
                settings.azure_openai_endpoint,
                settings.azure_openai_deployment,
                api_version=settings.azure_openai_api_version,
                token_provider=None
                if api_key
                else get_bearer_token_provider(credential, settings.openai_scope),
                api_key=api_key.get_secret_value() if api_key else None,
            ),
        )

    from .fake import FakeChatModel, FakeRetriever

    return FakeRetriever(settings.fake_corpus_dir), FakeChatModel()
