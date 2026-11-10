# Offline unit tests: `terraform test` against a mocked provider, no Azure credentials required.

mock_provider "azurerm" {}

variables {
  app_principal_id  = "11111111-1111-1111-1111-111111111111"
  openai_account_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/ai-rg/providers/Microsoft.CognitiveServices/accounts/larkspur-aoai"
  search_service_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/ai-rg/providers/Microsoft.Search/searchServices/larkspur-search"
}

run "app_reads_search_only_by_default" {
  command = plan

  assert {
    condition     = keys(azurerm_role_assignment.this) == ["app_search_reader"]
    error_message = "By default the app should only get Search Index Data Reader (Azure OpenAI goes through the gateway)."
  }

  assert {
    condition     = azurerm_role_assignment.this["app_search_reader"].role_definition_name == "Search Index Data Reader"
    error_message = "App must get read-only index access."
  }
}

run "direct_openai_is_opt_in" {
  command = plan

  variables {
    grant_app_direct_openai = true
  }

  assert {
    condition     = azurerm_role_assignment.this["app_openai_user"].scope == var.openai_account_id
    error_message = "Direct Azure OpenAI access should be scoped to the account."
  }
}

run "vectorizer_and_ingestion" {
  command = plan

  variables {
    search_service_principal_id = "33333333-3333-3333-3333-333333333333"
    ingestion_principal_id      = "44444444-4444-4444-4444-444444444444"
  }

  assert {
    condition     = length(azurerm_role_assignment.this) == 5
    error_message = "Expected reader + vectorizer + 3 ingestion assignments."
  }

  assert {
    condition     = azurerm_role_assignment.this["search_openai_user"].principal_id == "33333333-3333-3333-3333-333333333333"
    error_message = "Search identity needs Azure OpenAI access for the vectorizer."
  }

  assert {
    condition = alltrue([
      for k, v in azurerm_role_assignment.this : !contains(["Owner", "Contributor", "Cognitive Services Contributor"], v.role_definition_name)
    ])
    error_message = "No control-plane admin roles may be granted."
  }
}

run "rejects_bad_principal_type" {
  command = plan

  variables {
    principal_type = "Robot"
  }

  expect_failures = [var.principal_type]
}
