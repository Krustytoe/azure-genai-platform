# Offline unit tests: `terraform test` against a mocked provider, no Azure credentials required.

mock_provider "azurerm" {
  mock_resource "azurerm_cognitive_account" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/ai-rg/providers/Microsoft.CognitiveServices/accounts/larkspur-aoai"
    }
  }
}

variables {
  name                       = "larkspur-aoai"
  resource_group_name        = "ai-rg"
  location                   = "usgovvirginia"
  log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/ops-rg/providers/Microsoft.OperationalInsights/workspaces/ops"
  deployments = {
    chat = {
      model_name    = "gpt-4.1-mini"
      model_version = "2025-04-14"
    }
  }
}

run "keyless_and_private_by_default" {
  command = plan

  assert {
    condition     = azurerm_cognitive_account.this.local_auth_enabled == false
    error_message = "API keys must be disabled (Entra ID only)."
  }

  assert {
    condition     = azurerm_cognitive_account.this.public_network_access_enabled == false
    error_message = "Public network access must default to off."
  }

  assert {
    condition     = azurerm_cognitive_account.this.network_acls[0].default_action == "Deny"
    error_message = "Network ACLs must default-deny."
  }

  assert {
    condition     = azurerm_cognitive_account.this.custom_subdomain_name == var.name
    error_message = "A custom subdomain is required for Entra ID token auth."
  }
}

run "content_filters_cover_harms_and_prompt_shields" {
  command = plan

  assert {
    condition     = length(azurerm_cognitive_account_rai_policy.this.content_filter) == 12
    error_message = "Expected 4 harm categories x 2 directions + 4 shield/protected-material filters."
  }

  assert {
    condition = alltrue([
      for f in azurerm_cognitive_account_rai_policy.this.content_filter : f.block_enabled && f.filter_enabled
    ])
    error_message = "Every filter must be enabled and blocking."
  }

  assert {
    condition = anytrue([
      for f in azurerm_cognitive_account_rai_policy.this.content_filter : f.name == "Indirect Attack" && f.source == "Prompt"
    ])
    error_message = "Indirect prompt-injection shield must be on (RAG documents are untrusted)."
  }
}

run "deployments_pinned_and_filtered" {
  command = plan

  assert {
    condition     = azurerm_cognitive_deployment.this["chat"].version_upgrade_option == "NoAutoUpgrade"
    error_message = "Model versions must not auto-upgrade by default."
  }

  assert {
    condition     = azurerm_cognitive_deployment.this["chat"].rai_policy_name == "larkspur-aoai-baseline"
    error_message = "Every deployment must use the module's content filter policy."
  }

  assert {
    condition     = azurerm_cognitive_deployment.this["chat"].sku[0].name == "Standard"
    error_message = "Default deployment type should be regional Standard (data stays in region)."
  }
}

run "private_endpoint_and_diagnostics" {
  command = plan

  variables {
    private_endpoint = {
      subnet_id            = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/net-rg/providers/Microsoft.Network/virtualNetworks/hub/subnets/pe"
      private_dns_zone_ids = ["/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/net-rg/providers/Microsoft.Network/privateDnsZones/privatelink.openai.azure.us"]
    }
  }

  assert {
    condition     = azurerm_private_endpoint.this[0].private_service_connection[0].subresource_names == tolist(["account"])
    error_message = "Private endpoint must target the account subresource."
  }

  assert {
    condition     = one(azurerm_monitor_diagnostic_setting.this.enabled_log).category_group == "allLogs"
    error_message = "All log categories must be sent to Log Analytics."
  }
}

run "rejects_invalid_deployment_type" {
  command = plan

  variables {
    deployments = {
      chat = {
        model_name    = "gpt-4.1-mini"
        model_version = "2025-04-14"
        sku_name      = "Premium"
      }
    }
  }

  expect_failures = [var.deployments]
}

run "rejects_invalid_severity" {
  command = plan

  variables {
    content_filter_severity = "None"
  }

  expect_failures = [var.content_filter_severity]
}
