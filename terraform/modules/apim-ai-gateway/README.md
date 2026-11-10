# apim-ai-gateway

## Requirements

Terraform >= 1.7, azurerm provider >= 4.33 (tested on 4.x and 5.x). Run `terraform test` for offline validation (no Azure credentials required).

Puts Azure OpenAI behind an **API Management AI gateway** on an existing APIM instance: managed-identity auth to the backend, one product and subscription **per team** with its own token-per-minute limit and monthly quota, token metrics per team and deployment, retries, and a circuit breaker.

## Why a gateway

Without one, every team gets direct Azure OpenAI access, and there's no way to stop one team's batch job from exhausting the shared quota, no per-team cost view, and no single place to enforce policy. The gateway gives each team a key it can lose without exposing Azure OpenAI, a hard token budget, and a line on the chargeback report.

## Gotchas this module handles

- **Teams never hold Azure OpenAI credentials.** The gateway authenticates to Azure OpenAI with its own managed identity (`authentication-managed-identity`). The caller's `api-key` header is stripped before forwarding, and the role assignment is created for you.
- **Drop-in for the OpenAI SDK.** The subscription key is read from the `api-key` header, and the API path is `/openai/deployments/{id}/...`, so `AzureOpenAI(azure_endpoint=<gateway>, api_key=<team key>)` works with no code changes.
- **Limits per team, not per gateway.** `llm-token-limit` lives in each team's *product* policy, keyed on the subscription ID, so teams get independent budgets.
- **Throttling storms.** Retries cover transient 429/5xx, and a backend circuit breaker opens after sustained failures and honours `Retry-After`, so clients back off instead of piling on.
- **Government cloud audience.** `cloud = "usgovernment"` switches the managed-identity token audience to `cognitiveservices.azure.us`.
- **Keys stay out of state outputs.** Subscription IDs are output, but keys aren't. Fetch them into Key Vault out of band.

`llm-emit-token-metric` needs an Application Insights logger on the APIM instance with custom metrics enabled.

## Inputs

| Name | Description | Default |
|---|---|---|
| `api_management_name` | Existing API Management instance. It must have a system-assigned managed identity. | n/a (required) |
| `resource_group_name` | Resource group of the API Management instance. | n/a (required) |
| `openai_endpoint` | Azure OpenAI endpoint, e.g. https://<name>.openai.azure.com/ (module output openai-service.endpoint). | n/a (required) |
| `openai_account_id` | Azure OpenAI account resource ID. The gateway's identity is granted Cognitive Services OpenAI User on it. | n/a (required) |
| `cloud` | Azure cloud: public or usgovernment. Sets the token audience the gateway requests for Azure OpenAI. | `"public"` |
| `api_path` | Gateway path prefix. Keep "openai" so the OpenAI SDK's Azure client works unchanged against the gateway. | `"openai"` |
| `teams` | One APIM product + subscription per consuming team, each with its own token-per-minute limit and optional monthly token quota. | `{}` |
| `metric_namespace` | Application Insights custom-metric namespace for token usage. | `"genai-gateway"` |
| `retry_count` | Retries on 429/5xx from Azure OpenAI before the error is returned. The backend circuit breaker trips on sustained throttling. | `2` |

## Outputs

| Name | Description |
|---|---|
| `gateway_url` | Base URL apps use as their Azure OpenAI endpoint (RAG_AZURE_OPENAI_ENDPOINT). |
| `api_id` | API Management API ID. |
| `team_subscription_ids` | Subscription resource IDs per team. Keys stay out of Terraform outputs; fetch them from the portal or with az rest into Key Vault. |
