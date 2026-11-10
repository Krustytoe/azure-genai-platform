# ragapi (Azure)

FastAPI service that answers employee questions from an Azure AI Search index using Azure OpenAI, with citations, content filtering, PII redaction, and per-tenant token/cost telemetry. Production traffic goes through the APIM AI gateway in `terraform/modules/apim-ai-gateway`.

## Request path

1. **Redact** emails, SSNs, card numbers (Luhn-checked), phone numbers and cloud keys from the question, locally.
2. **Retrieve** from AI Search with a hybrid query (keyword + vector) re-ranked by the **semantic ranker**. The index's vectorizer embeds the query server-side using the search service's own managed identity, so the app never handles embeddings or Azure OpenAI keys for retrieval.
3. **Gate**: reranker scores (0-4) are normalised to 0-1. Chunks under `RAG_MIN_SCORE` are dropped, and if nothing is left the API refuses **without calling the model**.
4. **Generate** with Azure OpenAI through the gateway. The deployment's content filter (harm categories, Prompt Shields for jailbreaks and indirect attacks, protected material) applies, and a filtered prompt or completion comes back as `blocked: true`.
5. **Cite**: `[n]` markers are mapped back to their sources. An answer with no valid citation is reported as `grounded: false`.
6. **Account**: token usage and estimated cost are emitted as OpenTelemetry metrics tagged by `X-Tenant-Id`. APIM also emits per-subscription token metrics, so spend is visible at the gateway and in the app.

Logs record outcome, tenant, token counts and latency, **never** question or answer text.

## Run locally (no cloud account needed)

```bash
uv sync
RAG_PROVIDER=fake uv run uvicorn --factory ragapi.main:create_app --port 8080

curl -s localhost:8080/v1/chat -H 'content-type: application/json' -H 'x-tenant-id: finance' \
  -d '{"question":"What is the domestic meal per diem?"}' | jq
```

## Build the index

```bash
export RAG_AZURE_SEARCH_ENDPOINT=https://<search>.search.windows.net
export RAG_AZURE_OPENAI_RESOURCE_URI=https://<aoai>.openai.azure.com/
uv run python -m ragapi.ingest ../evals/corpus
```

This creates the index (HNSW cosine vectors, Azure OpenAI vectorizer, semantic config), then chunks, embeds and upserts the documents. It's idempotent. Run it as an identity with the ingestion roles from `rag-app-access`, from a network that can reach both private endpoints.

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `RAG_PROVIDER` | `fake` | `azure` in deployed environments |
| `RAG_AZURE_CLOUD` | `public` | `usgovernment` switches token scopes and authority |
| `RAG_AZURE_OPENAI_ENDPOINT` | | The APIM gateway URL (or the account endpoint for direct access) |
| `RAG_AZURE_OPENAI_DEPLOYMENT` | `chat` | Deployment name |
| `RAG_AZURE_OPENAI_API_VERSION` | `2024-10-21` | |
| `RAG_AZURE_OPENAI_API_KEY` | | The team's **APIM subscription key**, from Key Vault. Unset means Entra ID token auth |
| `RAG_AZURE_SEARCH_ENDPOINT` | | Required for `azure` |
| `RAG_AZURE_SEARCH_INDEX` | `handbook` | |
| `RAG_AZURE_SEARCH_SEMANTIC_CONFIG` | `default` | Empty switches to vector-only; then raise `RAG_MIN_SCORE` (~0.8), because cosine scores sit high |
| `RAG_AZURE_OPENAI_RESOURCE_URI` | | Ingestion only: the account endpoint the vectorizer and embedding calls use |
| `RAG_AZURE_EMBEDDING_DEPLOYMENT` / `_MODEL` / `_DIMENSIONS` | `embeddings` / `text-embedding-3-large` / `1024` | Ingestion only |
| `RAG_TOP_K`, `RAG_MIN_SCORE`, `RAG_MAX_QUESTION_CHARS`, `RAG_MAX_OUTPUT_TOKENS`, `RAG_TEMPERATURE` | `5`, `0.35`, `2000`, `800`, `0.1` | |
| `RAG_REDACT_PII` | `true` | |
| `RAG_PRICE_INPUT_PER_1K` / `RAG_PRICE_OUTPUT_PER_1K` | `0.0004` / `0.0016` | USD, for the `rag.cost` metric |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | | Enables OTLP/HTTP export (Azure Monitor via the OTel collector, Grafana, Langfuse) |

## API

Identical to the [AWS build](https://github.com/Krustytoe/aws-genai-platform/tree/main/app#api): `POST /v1/chat` with optional `X-Tenant-Id`. It returns `answer`, `grounded`, `blocked`, `citations`, `usage` and `redactions`. Errors are `422` invalid input, `429` throttling (with `Retry-After`), and `502` upstream failure.

## Tests

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest          # offline; the OpenAI SDK and httpx run against mock transports
```
