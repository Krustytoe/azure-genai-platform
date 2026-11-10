variable "name" {
  description = "Account name. Also the custom subdomain (required for Entra ID auth), so it must be globally unique."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$", var.name))
    error_message = "name must be 3-64 lowercase letters, digits or hyphens, starting and ending with a letter or digit."
  }
}

variable "resource_group_name" {
  description = "Resource group for the account and its private endpoint."
  type        = string
}

variable "location" {
  description = "Azure region, e.g. eastus2 or usgovvirginia. Model availability varies by region."
  type        = string
}

variable "kind" {
  description = "Account kind. OpenAI is the classic Azure OpenAI resource; AIServices is the multi-service Foundry resource."
  type        = string
  default     = "OpenAI"

  validation {
    condition     = contains(["OpenAI", "AIServices"], var.kind)
    error_message = "kind must be OpenAI or AIServices."
  }
}

variable "deployments" {
  description = "Model deployments keyed by deployment name. Upgrades are off by default so a model version change goes through change control."
  type = map(object({
    model_name             = string
    model_version          = string
    sku_name               = optional(string, "Standard")
    capacity               = optional(number, 10)
    version_upgrade_option = optional(string, "NoAutoUpgrade")
  }))
  default = {}

  validation {
    condition = alltrue([
      for d in values(var.deployments) : contains(
        ["Standard", "DataZoneStandard", "GlobalStandard", "ProvisionedManaged", "DataZoneProvisionedManaged", "GlobalProvisionedManaged", "GlobalBatch", "DataZoneBatch"],
        d.sku_name
      )
    ])
    error_message = "Each deployment sku_name must be a valid Azure OpenAI deployment type (Standard, DataZoneStandard, GlobalStandard, ...)."
  }

  validation {
    condition     = alltrue([for d in values(var.deployments) : contains(["NoAutoUpgrade", "OnceNewDefaultVersionAvailable", "OnceCurrentVersionExpired"], d.version_upgrade_option)])
    error_message = "version_upgrade_option must be NoAutoUpgrade, OnceNewDefaultVersionAvailable or OnceCurrentVersionExpired."
  }
}

variable "content_filter_severity" {
  description = "Lowest severity blocked by the hate, sexual, violence and self-harm filters, on prompts and completions. Low is strictest; Medium matches the Azure default."
  type        = string
  default     = "Medium"

  validation {
    condition     = contains(["Low", "Medium", "High"], var.content_filter_severity)
    error_message = "content_filter_severity must be Low, Medium or High."
  }
}

variable "public_network_access_enabled" {
  description = "Allow access from public networks. Secure default false: reach the account through the private endpoint."
  type        = bool
  default     = false
}

variable "allowed_ip_rules" {
  description = "Public IPs/CIDRs allowed when public access is enabled (e.g. a corporate egress range)."
  type        = list(string)
  default     = []
}

variable "private_endpoint" {
  description = "Private endpoint placement. private_dns_zone_ids should contain privatelink.openai.azure.com (privatelink.openai.azure.us in Azure Government). null skips the endpoint."
  type = object({
    subnet_id            = string
    private_dns_zone_ids = list(string)
  })
  default = null
}

variable "log_analytics_workspace_id" {
  description = "Workspace for audit logs and metrics. Required: an AI endpoint without an audit trail doesn't pass review."
  type        = string
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default     = {}
}
