# openai-service

## Requirements

Terraform >= 1.7, azurerm provider >= 4.33 (tested on 4.x and 5.x). Run `terraform test` for offline validation (no Azure credentials required).

An Azure OpenAI account locked down for enterprise use: keyless (Entra ID only), private by default, a strict content filter policy attached to every deployment, pinned model versions, and full diagnostics.

## Gotchas this module handles

- **Keys are the leak.** `local_auth_enabled = false` turns off API keys entirely, so every call is an auditable Entra ID identity. The custom subdomain that token auth requires is set from `name`.
- **RAG needs indirect-attack protection.** Retrieved documents are untrusted input. The content filter policy turns on **Prompt Shields** for both direct jailbreaks and *indirect* attacks (instructions hidden in documents), plus protected-material detection, in addition to the four harm categories in both directions.
- **Silent model upgrades.** Deployments default to `NoAutoUpgrade`, so a model version change goes through change control and your eval suite instead of happening in place.
- **Data residency.** The default deployment type is regional `Standard`, not `GlobalStandard`, so prompts are processed in the deployment's region unless you opt in to global routing.
- **No audit trail, no approval.** A diagnostic setting sending `allLogs` and `AllMetrics` to Log Analytics is mandatory, not optional.

## Usage

```hcl
module "openai" {
  source = "git::https://github.com/Krustytoe/azure-genai-platform.git//terraform/modules/openai-service?ref=v0.1.0" # x-release-please-version

  name                       = "larkspur-aoai"
  resource_group_name        = "ai-rg"
  location                   = "eastus2"
  log_analytics_workspace_id = azurerm_log_analytics_workspace.ops.id
  deployments = {
    chat = { model_name = "gpt-4.1-mini", model_version = "2025-04-14", capacity = 50 }
  }
  private_endpoint = {
    subnet_id            = module.vnet.subnet_ids["private-endpoints"]
    private_dns_zone_ids = [azurerm_private_dns_zone.openai.id]
  }
}
```

Creating several deployments on one account at once can hit "another operation is in progress" conflicts. If that happens, re-run the apply; it converges.

## Inputs

| Name | Description | Default |
|---|---|---|
| `name` | Account name. Also the custom subdomain (required for Entra ID auth), so it must be globally unique. | n/a (required) |
| `resource_group_name` | Resource group for the account and its private endpoint. | n/a (required) |
| `location` | Azure region, e.g. eastus2 or usgovvirginia. Model availability varies by region. | n/a (required) |
| `kind` | Account kind. OpenAI is the classic Azure OpenAI resource; AIServices is the multi-service Foundry resource. | `"OpenAI"` |
| `deployments` | Model deployments keyed by deployment name. Upgrades are off by default so a model version change goes through change control. | `{}` |
| `content_filter_severity` | Lowest severity blocked by the hate, sexual, violence and self-harm filters, on prompts and completions. Low is strictest; Medium matches the Azure default. | `"Medium"` |
| `public_network_access_enabled` | Allow access from public networks. Secure default false: reach the account through the private endpoint. | `false` |
| `allowed_ip_rules` | Public IPs/CIDRs allowed when public access is enabled (e.g. a corporate egress range). | `[]` |
| `private_endpoint` | Private endpoint placement. private_dns_zone_ids should contain privatelink.openai.azure.com (privatelink.openai.azure.us in Azure Government). null skips the endpoint. | `null` |
| `log_analytics_workspace_id` | Workspace for audit logs and metrics. Required: an AI endpoint without an audit trail doesn't pass review. | n/a (required) |
| `tags` | Tags applied to every resource. | `{}` |

## Outputs

| Name | Description |
|---|---|
| `id` | Account resource ID, used as the scope for role assignments. |
| `name` | Account name. |
| `endpoint` | Data-plane endpoint, e.g. https://<name>.openai.azure.com/. |
| `principal_id` | Object ID of the account's system-assigned identity. |
| `deployment_names` | Deployment names, i.e. the model value the app sends. |
| `rai_policy_name` | Content filter policy attached to every deployment. |
