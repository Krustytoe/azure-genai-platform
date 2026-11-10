# rag-app-access

## Requirements

Terraform >= 1.7, azurerm provider >= 4.33 (tested on 4.x and 5.x). Run `terraform test` for offline validation (no Azure credentials required).

Data-plane role assignments for the RAG workload: the app reads the index, the search service's identity calls Azure OpenAI for vectorization, and an optional ingestion identity builds the index. There are no control-plane roles and no keys.

## Gotchas this module handles

- **The gateway is the only door.** By default the app gets **no** direct Azure OpenAI role, so all chat traffic must go through the APIM gateway and its per-team limits. `grant_app_direct_openai = true` opts out.
- **Three identities, three jobs.** The app (read the index), the search service (embed queries via the vectorizer) and the ingestion identity (write the index, manage its schema, embed documents) each get only what their job needs.
- **Replication delay.** `principal_type` is set on every assignment, which avoids the intermittent "principal not found" failure when an identity was created moments earlier.

## Inputs

| Name | Description | Default |
|---|---|---|
| `app_principal_id` | Object ID of the RAG API's managed identity (Container Apps, AKS workload identity, App Service). | n/a (required) |
| `openai_account_id` | Azure OpenAI account resource ID. | n/a (required) |
| `search_service_id` | AI Search service resource ID. | n/a (required) |
| `grant_app_direct_openai` | Let the app call Azure OpenAI directly. Set false when all traffic must go through the APIM gateway, so the gateway is the only path. | `false` |
| `search_service_principal_id` | Object ID of the search service's managed identity. Granted Azure OpenAI access so the index vectorizer can embed queries. null skips it. | `null` |
| `ingestion_principal_id` | Object ID of the identity that builds the index (CI pipeline or a job). Gets index write/manage on search and embeddings on Azure OpenAI. null skips it. | `null` |
| `principal_type` | Principal type for the app and ingestion identities. Setting it avoids failures from Entra ID replication delay on fresh identities. | `"ServicePrincipal"` |

## Outputs

| Name | Description |
|---|---|
| `role_assignment_ids` | Role assignment IDs keyed by purpose. |
