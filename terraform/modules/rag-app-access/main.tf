# Data-plane roles only. Nothing here can change the resources themselves,
# and nobody needs (or can use) API keys: both services run with local auth off.

locals {
  assignments = merge(
    {
      app_search_reader = {
        scope     = var.search_service_id
        role      = "Search Index Data Reader"
        principal = var.app_principal_id
        type      = var.principal_type
      }
    },
    var.grant_app_direct_openai ? {
      app_openai_user = {
        scope     = var.openai_account_id
        role      = "Cognitive Services OpenAI User"
        principal = var.app_principal_id
        type      = var.principal_type
      }
    } : {},
    var.search_service_principal_id == null ? {} : {
      search_openai_user = {
        scope     = var.openai_account_id
        role      = "Cognitive Services OpenAI User"
        principal = var.search_service_principal_id
        type      = "ServicePrincipal"
      }
    },
    var.ingestion_principal_id == null ? {} : {
      ingest_search_contributor = {
        scope     = var.search_service_id
        role      = "Search Index Data Contributor"
        principal = var.ingestion_principal_id
        type      = var.principal_type
      }
      # Create/update index definitions (fields, vectorizer, semantic config).
      ingest_search_service_contributor = {
        scope     = var.search_service_id
        role      = "Search Service Contributor"
        principal = var.ingestion_principal_id
        type      = var.principal_type
      }
      ingest_openai_user = {
        scope     = var.openai_account_id
        role      = "Cognitive Services OpenAI User"
        principal = var.ingestion_principal_id
        type      = var.principal_type
      }
    },
  )
}

resource "azurerm_role_assignment" "this" {
  for_each = local.assignments

  scope                = each.value.scope
  role_definition_name = each.value.role
  principal_id         = each.value.principal
  principal_type       = each.value.type
}
