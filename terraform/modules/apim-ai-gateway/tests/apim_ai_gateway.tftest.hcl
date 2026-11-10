# Offline unit tests: `terraform test` against a mocked provider, no Azure credentials required.

mock_provider "azurerm" {
  mock_data "azurerm_api_management" {
    defaults = {
      gateway_url = "https://larkspur-apim.azure-api.us"
      identity = [{
        type         = "SystemAssigned"
        principal_id = "11111111-1111-1111-1111-111111111111"
        tenant_id    = "22222222-2222-2222-2222-222222222222"
        identity_ids = []
      }]
    }
  }

  mock_resource "azurerm_api_management_product" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/apim-rg/providers/Microsoft.ApiManagement/service/larkspur-apim/products/genai-finance"
    }
  }
}

variables {
  api_management_name = "larkspur-apim"
  resource_group_name = "apim-rg"
  openai_endpoint     = "https://larkspur-aoai.openai.azure.us/"
  openai_account_id   = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/ai-rg/providers/Microsoft.CognitiveServices/accounts/larkspur-aoai"
  cloud               = "usgovernment"
  teams = {
    finance = { tokens_per_minute = 20000, monthly_token_quota = 50000000 }
    support = { tokens_per_minute = 5000 }
  }
}

run "managed_identity_backend_auth" {
  command = plan

  assert {
    condition     = strcontains(azurerm_api_management_api_policy.openai.xml_content, "<authentication-managed-identity resource=\"https://cognitiveservices.azure.us\" />")
    error_message = "Gateway must authenticate to Azure OpenAI with its identity, using the Government audience."
  }

  assert {
    condition     = strcontains(azurerm_api_management_api_policy.openai.xml_content, "<set-header name=\"api-key\" exists-action=\"delete\" />")
    error_message = "Caller keys must not be forwarded to the backend."
  }

  assert {
    condition     = azurerm_role_assignment.gateway_openai_user.principal_id == "11111111-1111-1111-1111-111111111111" && azurerm_role_assignment.gateway_openai_user.role_definition_name == "Cognitive Services OpenAI User"
    error_message = "Gateway identity needs the OpenAI User data-plane role."
  }

  assert {
    condition     = azurerm_api_management_backend.openai.url == "https://larkspur-aoai.openai.azure.us/openai"
    error_message = "Backend URL should be the account endpoint plus /openai, without a double slash."
  }
}

run "sdk_compatible_surface" {
  command = plan

  assert {
    condition     = azurerm_api_management_api.openai.subscription_key_parameter_names[0].header == "api-key"
    error_message = "Subscription key header must be api-key so the OpenAI SDK works unchanged."
  }

  assert {
    condition     = azurerm_api_management_api_operation.this["chat-completions"].url_template == "/deployments/{deployment-id}/chat/completions"
    error_message = "Chat completions route must match the Azure OpenAI REST path."
  }

  assert {
    condition     = output.gateway_url == "https://larkspur-apim.azure-api.us/"
    error_message = "Gateway URL output should have exactly one trailing slash."
  }
}

run "per_team_token_limits" {
  command = plan

  assert {
    condition     = length(azurerm_api_management_product.team) == 2 && length(azurerm_api_management_subscription.team) == 2
    error_message = "Each team gets one product and one subscription."
  }

  assert {
    condition     = strcontains(azurerm_api_management_product_policy.team["finance"].xml_content, "tokens-per-minute=\"20000\"") && strcontains(azurerm_api_management_product_policy.team["finance"].xml_content, "token-quota=\"50000000\" token-quota-period=\"Monthly\"")
    error_message = "Finance should get its TPM limit and monthly quota."
  }

  assert {
    condition     = !strcontains(azurerm_api_management_product_policy.team["support"].xml_content, "token-quota")
    error_message = "Teams without a quota should only get a TPM limit."
  }

  assert {
    condition     = strcontains(azurerm_api_management_product_policy.team["support"].xml_content, "counter-key=\"@(context.Subscription.Id)\"")
    error_message = "Limits must be counted per subscription (per team)."
  }
}

run "public_cloud_audience" {
  command = plan

  variables {
    cloud = "public"
  }

  assert {
    condition     = strcontains(azurerm_api_management_api_policy.openai.xml_content, "https://cognitiveservices.azure.com")
    error_message = "Public cloud should use the commercial audience."
  }
}

run "requires_gateway_identity" {
  command = plan

  override_data {
    target = data.azurerm_api_management.this
    values = {
      identity = []
    }
  }

  expect_failures = [azurerm_role_assignment.gateway_openai_user]
}

run "rejects_bad_team_key" {
  command = plan

  variables {
    teams = { "Finance Team" = { tokens_per_minute = 1000 } }
  }

  expect_failures = [var.teams]
}
