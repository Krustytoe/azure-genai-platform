output "id" {
  description = "Account resource ID, used as the scope for role assignments."
  value       = azurerm_cognitive_account.this.id
}

output "name" {
  description = "Account name."
  value       = azurerm_cognitive_account.this.name
}

output "endpoint" {
  description = "Data-plane endpoint, e.g. https://<name>.openai.azure.com/."
  value       = azurerm_cognitive_account.this.endpoint
}

output "principal_id" {
  description = "Object ID of the account's system-assigned identity."
  value       = azurerm_cognitive_account.this.identity[0].principal_id
}

output "deployment_names" {
  description = "Deployment names, i.e. the model value the app sends."
  value       = keys(azurerm_cognitive_deployment.this)
}

output "rai_policy_name" {
  description = "Content filter policy attached to every deployment."
  value       = azurerm_cognitive_account_rai_policy.this.name
}
