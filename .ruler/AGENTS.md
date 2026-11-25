# azure-genai-platform

Retrieval-augmented generation (RAG) platform on Azure OpenAI and Azure AI Search: Terraform modules for keyless, private, content-filtered AI infrastructure behind an APIM AI gateway, a FastAPI service (`ragapi`) that answers only from approved documents with citations, and a promptfoo eval suite that gates every change. Must work unchanged in Azure commercial and Azure Government.

## Layout

- `terraform/modules/<module>/` - `openai-service`, `ai-search`, `apim-ai-gateway` (APIM policies in `policies/*.xml.tftpl`), `rag-app-access`. Each has `main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`, `README.md`, and `tests/*.tftest.hcl` (mocked provider).
- `terraform/examples/complete/` - wires all modules together; outputs `app_environment` and `pending_approvals`.
- `app/` - Python API (uv project, `pyproject.toml`, `uv.lock`, `Dockerfile`).
  - `app/src/ragapi/` - `main.py` (FastAPI, `create_app` factory), `pipeline.py`, `config.py` (`RAG_*` settings), `ingest.py` (index builder, `ragapi-ingest`), `redaction.py`, `chunking.py`, `prompts.py`, `telemetry.py`.
  - `app/src/ragapi/providers/` - `base.py` (`Retriever` / `ChatModel` protocols), `azure.py`, `fake.py` (offline provider).
  - `app/tests/` - pytest suite; the OpenAI SDK and httpx run against mock transports.
- `evals/` - `promptfooconfig.yaml`, `tests.yaml`, and the sample policy corpus in `evals/corpus/`.
- `.github/workflows/` - `terraform`, `app`, `security`, `evals-deployed`, `release-please`, `dependabot-auto-merge`, `ruler`.

## Commands

All of these run offline with no cloud credentials unless marked otherwise. They match what CI runs.

Terraform (Terraform >= 1.7, tflint v0.64.0):

```bash
terraform fmt -check -recursive -diff terraform
cd terraform/modules/<module>            # or terraform/examples/complete
terraform init -backend=false -input=false
terraform validate
terraform test                            # modules with tests/*.tftest.hcl; mocked provider
tflint --init --config "$(git rev-parse --show-toplevel)/.tflint.hcl"
tflint --config "$(git rev-parse --show-toplevel)/.tflint.hcl"
```

App (uv):

```bash
cd app
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run pytest                             # enforces --cov-fail-under=90
```

Evals against the local API (Node.js LTS):

```bash
(cd app && RAG_PROVIDER=fake uv run uvicorn --factory ragapi.main:create_app --port 8080 &)
RAG_API_URL=http://localhost:8080 npx promptfoo@0.125.1 eval -c evals/promptfooconfig.yaml
```

Container image (CI builds it, checks it runs as UID 10001, and smoke-tests `/healthz` and `/v1/chat` with the fake provider):

```bash
docker build -t ragapi:ci app
```

Require deployed infrastructure or Azure credentials - run only with explicit human approval:

- `terraform plan` / `terraform apply` in `terraform/examples/complete`.
- Index build: `uv run python -m ragapi.ingest ../evals/corpus` (from `app/`, as the ingestion identity, with `RAG_AZURE_SEARCH_ENDPOINT` and `RAG_AZURE_OPENAI_RESOURCE_URI` set).
- `RAG_PROVIDER=azure` runs of the API.
- The `evals-deployed` workflow (promptfoo against a deployed `api_url`).

## Conventions

- Secure by default: any input that weakens a control (local auth on, content filter off, public access on, diagnostics off) defaults to the secure value and says so in its description.
- Every module change ships with a `tests/*.tftest.hcl` run asserting the behaviour, including the negative case for any `validation` block.
- Every API behaviour change ships with a pytest test, plus a promptfoo case in `evals/tests.yaml` if it changes what users see (refusals, citations, redaction).
- Cloud-aware: never hard-code `*.azure.com` or `*.windows.net` endpoints, audiences, or scopes. Derive them from the `cloud` Terraform variable / `RAG_AZURE_CLOUD` setting (`public` or `usgovernment`).
- Keyless: Azure OpenAI and AI Search run with local auth off and use Entra ID / managed identities. The only key is a team's APIM subscription key (`RAG_AZURE_OPENAI_API_KEY`), handled as `SecretStr`.
- Model deployments default to `version_upgrade_option = "NoAutoUpgrade"`; a model version change is a reviewed change that must pass evals.
- No prompt or answer text in logs, metric attributes, or span attributes. Use counts, IDs, and outcomes.
- Provider constraints are bounded: floor the version you need and cap the next major (e.g. `>= 4.33, < 6.0`).
- The pipeline depends only on the `Retriever` and `ChatModel` protocols in `providers/base.py`; keep cloud SDK code inside provider adapters.
- Runtime config comes from `RAG_*` environment variables via `config.py` (pydantic-settings). Add new settings there with validation bounds.
- Python: ruff with `line-length = 100`, `target-version = "py312"`, rule sets `E,F,I,B,UP,S,SIM,RUF,PT`.
- Telemetry follows OpenTelemetry GenAI semantic conventions and exports over OTLP.
- Pin third-party GitHub Actions to a full commit SHA with the version as a trailing comment (`uses: org/action@<sha> # v1.2.3`).
- PR titles are Conventional Commits (`feat:`, `fix:`, `docs:`, `ci:`, `chore:`, `feat!:` for breaking). PRs are squash-merged and release-please uses the title for versioning and `CHANGELOG.md`.
- Do not hand-edit version strings marked `# x-release-please-version` or `CHANGELOG.md`; release-please manages them.
- Keep changes focused: one concern per PR. Update READMEs when inputs, outputs, or behaviour change.

## Guardrails

- Never run `terraform apply`, deploy, build the index, or call live Azure OpenAI / AI Search / APIM endpoints without explicit human approval. Use `terraform init -backend=false`, `validate`, and `test` (mocked provider) for verification.
- No secrets, keys, tokens, credentials, subscription/tenant IDs, or internal hostnames in code, tests, fixtures, logs, or command output. Use obvious placeholders.
- Model deployment names, model versions, API versions, and endpoints come from configuration (`RAG_*` settings, Terraform variables/outputs). Never hard-code or guess them.
- Do not weaken the content filter, local-auth-off, PII redaction, refusal-before-generation, or gateway token limits to make a test pass.
- Report security vulnerabilities privately per `SECURITY.md`, not in public issues.
- Generated agent files (`AGENTS.md`, `CLAUDE.md`, `.gemini/settings.json` at the repo root) are produced by Ruler from `.ruler/`. Edit `.ruler/AGENTS.md`, then run `npx @intellectronica/ruler@0.3.46 apply`. Never hand-edit the generated files; the `ruler` workflow fails on drift.

## Definition of done

- `terraform fmt -check`, `validate`, `terraform test`, and `tflint` pass for every touched module and `terraform/examples/complete`.
- `ruff check`, `ruff format --check`, and `pytest` (90% coverage) pass in `app/`.
- The promptfoo suite passes against the API running with `RAG_PROVIDER=fake`.
- New behaviour has tests (tftest, pytest, and promptfoo where user-visible).
- READMEs updated for changed inputs, outputs, configuration, or behaviour.
- No secrets or environment-specific identifiers in the diff.
- If `.ruler/` changed, Ruler output is regenerated and committed.
- PR title is a Conventional Commit.
