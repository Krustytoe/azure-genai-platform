output "gateway_url" {
  description = "Base URL apps use as their Azure OpenAI endpoint (RAG_AZURE_OPENAI_ENDPOINT)."
  value       = "${trimsuffix(data.azurerm_api_management.this.gateway_url, "/")}/"
}

output "api_id" {
  description = "API Management API ID."
  value       = azurerm_api_management_api.openai.id
}

output "team_subscription_ids" {
  description = "Subscription resource IDs per team. Keys stay out of Terraform outputs; fetch them from the portal or with az rest into Key Vault."
  value       = { for k, v in azurerm_api_management_subscription.team : k => v.id }
}
