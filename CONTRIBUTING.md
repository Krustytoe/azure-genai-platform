# Contributing

Thanks for taking a look. Issues and PRs are welcome. For anything bigger than a small fix, open an issue first so we can agree on the approach before you write code.

## Workflow

1. Branch from `main` (fork first if you don't have write access).
2. Make the change and run the local checks below. They're the same ones CI runs.
3. Open a PR using the template. **The PR title must be a [Conventional Commit](https://www.conventionalcommits.org/)** (`feat:`, `fix:`, `docs:`, `ci:`, `chore:`, `feat!:` for breaking changes). PRs are squash-merged, so the title becomes the commit, and [release-please](https://github.com/googleapis/release-please) uses it to pick the next version and write the changelog.
4. CI must be green and the PR reviewed before merge.

## Local checks

No cloud credentials are needed for any of these.

**Terraform** (Terraform >= 1.7, [tflint](https://github.com/terraform-linters/tflint) v0.64.0):

```bash
terraform fmt -check -recursive terraform

cd terraform/modules/<module>
terraform init -backend=false && terraform validate && terraform test
tflint --init --config "$(git rev-parse --show-toplevel)/.tflint.hcl"
tflint --config "$(git rev-parse --show-toplevel)/.tflint.hcl"
```

**App** ([uv](https://docs.astral.sh/uv/)):

```bash
cd app
uv sync
uv run ruff check . && uv run ruff format --check .
uv run pytest
```

**Evals** (Node.js LTS):

```bash
(cd app && RAG_PROVIDER=fake uv run uvicorn --factory ragapi.main:create_app --port 8080 &)
RAG_API_URL=http://localhost:8080 npx promptfoo@0.125.1 eval -c evals/promptfooconfig.yaml
```

## Conventions

- **Secure by default.** A new input that weakens a control (local auth on, content filter off, public access on, diagnostics off) must default to the secure value and say so in its description.
- **Every module change ships with a test.** Add or update a `tests/*.tftest.hcl` run that asserts the behaviour, including the negative case for any `validation` block.
- **Every behaviour change in the API ships with a test**, and a promptfoo case if it changes what users see (refusals, citations, redaction).
- **Cloud-aware.** Never hard-code `*.azure.com` or `*.windows.net` endpoints, audiences or scopes. Derive them from the `cloud` setting so modules and the app work in Azure Government.
- **No prompt or answer text in logs, metric attributes or span attributes.** Use counts, IDs and outcomes.
- **Bounded provider constraints.** Floor the version you actually need and cap the next major.

## Ground rules

- **No secrets in the repo, ever.** That includes tokens, keys, account/subscription/tenant IDs, and internal hostnames in examples or test fixtures. Use obvious placeholders.
- **Pin third-party GitHub Actions to a full commit SHA** with the version as a trailing comment (`uses: org/action@<sha> # v1.2.3`) so Dependabot can bump them.
- Keep changes focused: one concern per PR makes review and rollback easy.

## Security issues

Don't open a public issue. See [SECURITY.md](SECURITY.md).
