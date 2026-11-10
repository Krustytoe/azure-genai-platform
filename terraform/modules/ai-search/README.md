# ai-search

## Requirements

Terraform >= 1.7, azurerm provider >= 4.33 (tested on 4.x and 5.x). Run `terraform test` for offline validation (no Azure credentials required).

An Azure AI Search service for RAG: keyless (RBAC only), private by default, semantic ranker on, a managed identity for query-time vectorization, and optional **shared private links** so it can reach a private Azure OpenAI account.

## Gotchas this module handles

- **The private-to-private trap.** When Azure OpenAI has public access off, the search service's vectorizer can't reach it, and queries fail with a vague error. `shared_private_links` creates the outbound private link (`openai_account` subresource). The connection then needs **approval** on the Azure OpenAI side, and the IDs are output so you can automate that.
- **Relevance gating needs comparable scores.** Hybrid search scores (RRF) are tiny and not comparable across queries, so they're useless as a "nothing relevant" threshold. The semantic ranker's 0-4 reranker score is what the RAG API gates on, so it's on by default.
- **SLA by default.** Two replicas give the read SLA. The `free` tier is rejected because it has no SLA, no private endpoint and no managed identity.
- **Keys off.** `local_authentication_enabled = false`: admin and query keys can't be used, and access is via `Search Index Data Reader` / `Contributor` roles.

## Inputs

| Name | Description | Default |
|---|---|---|
| `name` | Search service name (globally unique, becomes <name>.search.windows.net). | n/a (required) |
| `resource_group_name` | Resource group for the service and its private endpoint. | n/a (required) |
| `location` | Azure region. | n/a (required) |
| `sku` | Pricing tier. basic is enough for a pilot; standard adds capacity and more indexes. | `"standard"` |
| `replica_count` | Replicas. 2 gives the read SLA, 3 gives read/write. Each replica is billed. | `2` |
| `partition_count` | Partitions (storage and indexing throughput). | `1` |
| `semantic_search_sku` | Semantic ranker plan (free or standard). The RAG API uses reranker scores to decide whether a chunk is relevant. null disables it. | `"standard"` |
| `public_network_access_enabled` | Allow access from public networks. Secure default false. | `false` |
| `allowed_ips` | Public IPs/CIDRs allowed when public access is enabled. | `[]` |
| `private_endpoint` | Private endpoint placement. private_dns_zone_ids should contain privatelink.search.windows.net (privatelink.search.azure.us in Azure Government). null skips the endpoint. | `null` |
| `shared_private_links` | Outbound private links from the search service, e.g. to a private Azure OpenAI account for query-time vectorization ({ aoai = { target_resource_id = ..., subresource_name = "openai_account" } }). The target owner must approve each connection. | `{}` |
| `log_analytics_workspace_id` | Workspace for audit logs and metrics. | n/a (required) |
| `tags` | Tags applied to every resource. | `{}` |

## Outputs

| Name | Description |
|---|---|
| `id` | Search service resource ID, used as the scope for role assignments. |
| `name` | Search service name. |
| `endpoint` | Data-plane endpoint (cloud-aware, e.g. https://<name>.search.azure.us in Azure Government). |
| `principal_id` | Object ID of the service's system-assigned identity (grant it Cognitive Services OpenAI User for vectorization). |
| `shared_private_link_ids` | Shared private link IDs; each needs approval on the target resource. |
