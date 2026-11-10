output "id" {
  description = "Search service resource ID, used as the scope for role assignments."
  value       = azurerm_search_service.this.id
}

output "name" {
  description = "Search service name."
  value       = azurerm_search_service.this.name
}

output "endpoint" {
  description = "Data-plane endpoint (cloud-aware, e.g. https://<name>.search.azure.us in Azure Government)."
  value       = azurerm_search_service.this.endpoint
}

output "principal_id" {
  description = "Object ID of the service's system-assigned identity (grant it Cognitive Services OpenAI User for vectorization)."
  value       = azurerm_search_service.this.identity[0].principal_id
}

output "shared_private_link_ids" {
  description = "Shared private link IDs; each needs approval on the target resource."
  value       = { for k, v in azurerm_search_shared_private_link_service.this : k => v.id }
}
