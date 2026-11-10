resource "azurerm_search_service" "this" {
  name                = var.name
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = var.sku
  replica_count       = var.replica_count
  partition_count     = var.partition_count
  semantic_search_sku = var.semantic_search_sku

  # Entra ID RBAC only: no admin or query keys.
  local_authentication_enabled  = false
  public_network_access_enabled = var.public_network_access_enabled
  allowed_ips                   = var.allowed_ips

  # The service's own identity calls Azure OpenAI to vectorize queries.
  identity {
    type = "SystemAssigned"
  }

  tags = var.tags
}

resource "azurerm_search_shared_private_link_service" "this" {
  for_each = var.shared_private_links

  name               = "${var.name}-${each.key}"
  search_service_id  = azurerm_search_service.this.id
  target_resource_id = each.value.target_resource_id
  subresource_name   = each.value.subresource_name
  request_message    = "Search service ${var.name} outbound private link"
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
    private_connection_resource_id = azurerm_search_service.this.id
    subresource_names              = ["searchService"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = var.private_endpoint.private_dns_zone_ids
  }
}

resource "azurerm_monitor_diagnostic_setting" "this" {
  name                       = "${var.name}-diag"
  target_resource_id         = azurerm_search_service.this.id
  log_analytics_workspace_id = var.log_analytics_workspace_id

  enabled_log {
    category_group = "allLogs"
  }

  enabled_metric {
    category = "AllMetrics"
  }
}
