# Offline unit tests: `terraform test` against a mocked provider, no Azure credentials required.

mock_provider "azurerm" {
  mock_resource "azurerm_search_service" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/ai-rg/providers/Microsoft.Search/searchServices/larkspur-search"
    }
  }
}

variables {
  name                       = "larkspur-search"
  resource_group_name        = "ai-rg"
  location                   = "usgovvirginia"
  log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/ops-rg/providers/Microsoft.OperationalInsights/workspaces/ops"
}

run "keyless_private_ha_defaults" {
  command = plan

  assert {
    condition     = azurerm_search_service.this.local_authentication_enabled == false
    error_message = "Admin/query keys must be disabled."
  }

  assert {
    condition     = azurerm_search_service.this.public_network_access_enabled == false
    error_message = "Public network access must default to off."
  }

  assert {
    condition     = azurerm_search_service.this.replica_count == 2
    error_message = "Default should meet the read SLA (2 replicas)."
  }

  assert {
    condition     = azurerm_search_service.this.semantic_search_sku == "standard"
    error_message = "Semantic ranker should be on; the API gates on reranker scores."
  }

  assert {
    condition     = azurerm_search_service.this.identity[0].type == "SystemAssigned"
    error_message = "A managed identity is required for query-time vectorization."
  }
}

run "shared_private_link_to_openai" {
  command = plan

  variables {
    shared_private_links = {
      aoai = {
        target_resource_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/ai-rg/providers/Microsoft.CognitiveServices/accounts/larkspur-aoai"
        subresource_name   = "openai_account"
      }
    }
  }

  assert {
    condition     = azurerm_search_shared_private_link_service.this["aoai"].subresource_name == "openai_account"
    error_message = "Shared private link should target the openai_account subresource."
  }
}

run "private_endpoint" {
  command = plan

  variables {
    private_endpoint = {
      subnet_id            = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/net-rg/providers/Microsoft.Network/virtualNetworks/hub/subnets/pe"
      private_dns_zone_ids = ["/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/net-rg/providers/Microsoft.Network/privateDnsZones/privatelink.search.azure.us"]
    }
  }

  assert {
    condition     = azurerm_private_endpoint.this[0].private_service_connection[0].subresource_names == tolist(["searchService"])
    error_message = "Private endpoint must target the searchService subresource."
  }
}

run "rejects_free_tier" {
  command = plan

  variables {
    sku = "free"
  }

  expect_failures = [var.sku]
}

run "rejects_double_hyphen_name" {
  command = plan

  variables {
    name = "bad--name"
  }

  expect_failures = [var.name]
}
