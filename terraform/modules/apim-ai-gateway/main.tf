data "azurerm_api_management" "this" {
  name                = var.api_management_name
  resource_group_name = var.resource_group_name
}

locals {
  audience = {
    public       = "https://cognitiveservices.azure.com"
    usgovernment = "https://cognitiveservices.azure.us"
  }[var.cloud]

  apim_principal_id = try(data.azurerm_api_management.this.identity[0].principal_id, "")
  backend_id        = "azure-openai"
}

# The gateway's identity is the only principal that needs data-plane access to
# Azure OpenAI; teams never hold Azure OpenAI credentials.
resource "azurerm_role_assignment" "gateway_openai_user" {
  scope                = var.openai_account_id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = local.apim_principal_id
  principal_type       = "ServicePrincipal"

  lifecycle {
    precondition {
      condition     = local.apim_principal_id != ""
      error_message = "API Management instance has no system-assigned managed identity. Enable it first."
    }
  }
}

resource "azurerm_api_management_backend" "openai" {
  name                = local.backend_id
  api_management_name = var.api_management_name
  resource_group_name = var.resource_group_name
  protocol            = "http"
  url                 = "${trimsuffix(var.openai_endpoint, "/")}/openai"
  description         = "Azure OpenAI data plane"

  tls {
    validate_certificate_chain = true
    validate_certificate_name  = true
  }

  # Stop hammering a throttled backend: open the circuit for a minute after
  # repeated 429/5xx and honour Retry-After.
  circuit_breaker_rule {
    name                       = "openai-throttling"
    trip_duration              = "PT1M"
    accept_retry_after_enabled = true

    failure_condition {
      count             = 5
      interval_duration = "PT1M"

      status_code_range {
        min = 429
        max = 429
      }

      status_code_range {
        min = 500
        max = 599
      }
    }
  }
}

resource "azurerm_api_management_api" "openai" {
  name                  = "azure-openai"
  api_management_name   = var.api_management_name
  resource_group_name   = var.resource_group_name
  revision              = "1"
  display_name          = "Azure OpenAI"
  description           = "Governed access to Azure OpenAI: per-team token limits, metrics, managed-identity backend auth."
  path                  = var.api_path
  protocols             = ["https"]
  subscription_required = true

  # The OpenAI SDK's Azure client sends its key as "api-key", so a team's APIM
  # subscription key works as a drop-in replacement for an Azure OpenAI key.
  subscription_key_parameter_names {
    header = "api-key"
    query  = "api-key"
  }
}

resource "azurerm_api_management_api_operation" "this" {
  for_each = {
    chat-completions = { display = "Chat completions", path = "chat/completions" }
    embeddings       = { display = "Embeddings", path = "embeddings" }
  }

  operation_id        = each.key
  api_name            = azurerm_api_management_api.openai.name
  api_management_name = var.api_management_name
  resource_group_name = var.resource_group_name
  display_name        = each.value.display
  method              = "POST"
  url_template        = "/deployments/{deployment-id}/${each.value.path}"

  template_parameter {
    name     = "deployment-id"
    type     = "string"
    required = true
  }
}

resource "azurerm_api_management_api_policy" "openai" {
  api_name            = azurerm_api_management_api.openai.name
  api_management_name = var.api_management_name
  resource_group_name = var.resource_group_name

  xml_content = templatefile("${path.module}/policies/api.xml.tftpl", {
    backend_id       = azurerm_api_management_backend.openai.name
    audience         = local.audience
    metric_namespace = var.metric_namespace
    retry_count      = var.retry_count
  })
}

# ---------------------------------------------------------------------------
# Per-team products: separate limits, separate keys, separate metrics.
# ---------------------------------------------------------------------------

resource "azurerm_api_management_product" "team" {
  for_each = var.teams

  product_id            = "genai-${each.key}"
  api_management_name   = var.api_management_name
  resource_group_name   = var.resource_group_name
  display_name          = "GenAI - ${each.key}"
  description           = "Azure OpenAI access for ${each.key}: ${each.value.tokens_per_minute} tokens/min"
  subscription_required = true
  approval_required     = false
  subscriptions_limit   = 1
  published             = true
}

resource "azurerm_api_management_product_api" "team" {
  for_each = var.teams

  product_id          = azurerm_api_management_product.team[each.key].product_id
  api_name            = azurerm_api_management_api.openai.name
  api_management_name = var.api_management_name
  resource_group_name = var.resource_group_name
}

resource "azurerm_api_management_product_policy" "team" {
  for_each = var.teams

  product_id          = azurerm_api_management_product.team[each.key].product_id
  api_management_name = var.api_management_name
  resource_group_name = var.resource_group_name

  xml_content = templatefile("${path.module}/policies/product.xml.tftpl", {
    tokens_per_minute   = each.value.tokens_per_minute
    monthly_token_quota = each.value.monthly_token_quota
  })
}

resource "azurerm_api_management_subscription" "team" {
  for_each = var.teams

  display_name        = "genai-${each.key}"
  api_management_name = var.api_management_name
  resource_group_name = var.resource_group_name
  product_id          = azurerm_api_management_product.team[each.key].id
  state               = "active"
  allow_tracing       = false
}
