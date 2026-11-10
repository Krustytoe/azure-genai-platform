"""Runtime configuration, read from RAG_* environment variables."""

from enum import StrEnum
from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Provider(StrEnum):
    AZURE = "azure"
    FAKE = "fake"  # offline: keyword retrieval over a local corpus, canned answers


class AzureCloud(StrEnum):
    PUBLIC = "public"
    USGOVERNMENT = "usgovernment"


# Entra ID token scopes per cloud: (Azure OpenAI, AI Search).
SCOPES: dict[AzureCloud, tuple[str, str]] = {
    AzureCloud.PUBLIC: (
        "https://cognitiveservices.azure.com/.default",
        "https://search.azure.com/.default",
    ),
    AzureCloud.USGOVERNMENT: (
        "https://cognitiveservices.azure.us/.default",
        "https://search.azure.us/.default",
    ),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAG_", extra="ignore")

    provider: Provider = Provider.FAKE

    # Azure
    azure_cloud: AzureCloud = AzureCloud.PUBLIC
    # The APIM gateway URL in production, or the account endpoint for direct access.
    azure_openai_endpoint: str | None = None
    azure_openai_deployment: str = "chat"
    azure_openai_api_version: str = "2024-10-21"
    # APIM subscription key (sent as api-key). Unset = Entra ID token auth.
    azure_openai_api_key: SecretStr | None = None
    azure_search_endpoint: str | None = None
    azure_search_index: str = "handbook"
    azure_search_semantic_config: str | None = "default"
    azure_search_api_version: str = "2024-07-01"

    # Ingestion (index build): talks to the Azure OpenAI account directly.
    azure_openai_resource_uri: str | None = None
    azure_embedding_deployment: str = "embeddings"
    azure_embedding_model: str = "text-embedding-3-large"
    azure_embedding_dimensions: int = Field(1024, ge=256, le=3072)

    # Fake provider
    fake_corpus_dir: Path = Path("../evals/corpus")

    # Retrieval and generation
    top_k: int = Field(5, ge=1, le=20)
    min_score: float = Field(0.35, ge=0.0, le=1.0)
    max_question_chars: int = Field(2000, ge=1, le=20_000)
    max_output_tokens: int = Field(800, ge=1, le=8192)
    temperature: float = Field(0.1, ge=0.0, le=1.0)

    # Data protection
    redact_pii: bool = True

    # Cost attribution (USD per 1K tokens). Set to your deployment's price.
    price_input_per_1k: float = Field(0.0004, ge=0.0)
    price_output_per_1k: float = Field(0.0016, ge=0.0)

    @field_validator("azure_search_semantic_config", mode="before")
    @classmethod
    def _empty_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @property
    def openai_scope(self) -> str:
        return SCOPES[self.azure_cloud][0]

    @property
    def search_scope(self) -> str:
        return SCOPES[self.azure_cloud][1]

    @model_validator(mode="after")
    def _require_cloud_settings(self) -> "Settings":
        if self.provider is Provider.AZURE:
            missing = [
                name
                for name, value in (
                    ("RAG_AZURE_OPENAI_ENDPOINT", self.azure_openai_endpoint),
                    ("RAG_AZURE_SEARCH_ENDPOINT", self.azure_search_endpoint),
                )
                if not value
            ]
            if missing:
                raise ValueError(f"provider=azure requires {', '.join(missing)}")
        return self
