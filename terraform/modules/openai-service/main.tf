locals {
  harm_categories = ["Hate", "Sexual", "Violence", "SelfHarm"]

  # Severity filters for each harm category, in both directions.
  harm_filters = flatten([
    for c in local.harm_categories : [
      for s in ["Prompt", "Completion"] : {
        name               = c
        source             = s
        severity_threshold = var.content_filter_severity
      }
    ]
  ])

  # Prompt Shields (direct jailbreaks and indirect attacks hidden in documents)
  # and protected-material detection. Severity is ignored for these; the API
  # still requires a value.
  shield_filters = [
    { name = "Jailbreak", source = "Prompt", severity_threshold = "High" },
    { name = "Indirect Attack", source = "Prompt", severity_threshold = "High" },
    { name = "Protected Material Text", source = "Completion", severity_threshold = "High" },
    { name = "Protected Material Code", source = "Completion", severity_threshold = "High" },
  ]
}

resource "azurerm_cognitive_account" "this" {
  name                  = var.name
  resource_group_name   = var.resource_group_name
  location              = var.location
  kind                  = var.kind
  sku_name              = "S0"
  custom_subdomain_name = var.name

  # Entra ID only: no API keys to leak, rotate, or share between teams.
  local_auth_enabled            = false
  public_network_access_enabled = var.public_network_access_enabled

  # Chat completion doesn't need the account to call out anywhere.
  outbound_network_access_restricted = true

  network_acls {
    default_action = "Deny"
    ip_rules       = var.allowed_ip_rules
  }

  identity {
    type = "SystemAssigned"
  }

  tags = var.tags
}

resource "azurerm_cognitive_account_rai_policy" "this" {
  name                 = "${var.name}-baseline"
  cognitive_account_id = azurerm_cognitive_account.this.id
  base_policy_name     = "Microsoft.DefaultV2"
  tags                 = var.tags

  dynamic "content_filter" {
    for_each = concat(local.harm_filters, local.shield_filters)
    content {
      name               = content_filter.value.name
      source             = content_filter.value.source
      severity_threshold = content_filter.value.severity_threshold
      filter_enabled     = true
      block_enabled      = true
    }
  }
}

resource "azurerm_cognitive_deployment" "this" {
  for_each = var.deployments

  name                   = each.key
  cognitive_account_id   = azurerm_cognitive_account.this.id
  rai_policy_name        = azurerm_cognitive_account_rai_policy.this.name
  version_upgrade_option = each.value.version_upgrade_option

  model {
    format  = "OpenAI"
    name    = each.value.model_name
    version = each.value.model_version
  }

  sku {
    name     = each.value.sku_name
    capacity = each.value.capacity
  }
}

resource "azurerm_private_endpoint" "this" {
  count = var.private_endpoint == null ? 0 : 1

  name                = "${var.name}-pe"
  resource_group_name = var.resource_group_name
  location            = var.location
  subnet_id           = var.private_endpoint.subnet_id
  tags                = var.tags

  private_service_connection {
    name                           = "${var.name}-psc"
    private_connection_resource_id = azurerm_cognitive_account.this.id
    subresource_names              = ["account"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = var.private_endpoint.private_dns_zone_ids
  }
}

resource "azurerm_monitor_diagnostic_setting" "this" {
  name                       = "${var.name}-diag"
  target_resource_id         = azurerm_cognitive_account.this.id
  log_analytics_workspace_id = var.log_analytics_workspace_id

  enabled_log {
    category_group = "allLogs"
  }

  enabled_metric {
    category = "AllMetrics"
  }
}
