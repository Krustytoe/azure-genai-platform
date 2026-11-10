# End-to-end wiring: Azure OpenAI + AI Search behind private endpoints, an APIM
# AI gateway with per-team token limits, and least-privilege identities.
#
# Bring your own network (e.g. Krustytoe/terraform-azure-platform-modules//modules/vnet-baseline),
# private DNS zones, Log Analytics workspace and API Management instance.
# For Azure Government set cloud = "usgovernment" and configure the provider
# with environment = "usgovernment".

terraform {
  required_version = ">= 1.7"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 4.33, < 6.0"
    }
  }
}

provider "azurerm" {
  features {}
  environment = var.cloud
}

variable "cloud" {
  description = "public or usgovernment."
  type        = string
  default     = "public"
}

variable "location" {
  description = "Region with the chosen models available."
  type        = string
  default     = "eastus2"
}

variable "resource_group_name" {
  description = "Resource group for the AI resources."
  type        = string
}

variable "log_analytics_workspace_id" {
  description = "Central Log Analytics workspace."
  type        = string
}

variable "private_endpoint_subnet_id" {
  description = "Subnet for private endpoints."
  type        = string
}

variable "openai_private_dns_zone_id" {
  description = "privatelink.openai.azure.com (or .azure.us) zone ID."
  type        = string
}

variable "search_private_dns_zone_id" {
  description = "privatelink.search.windows.net (or privatelink.search.azure.us) zone ID."
  type        = string
}

variable "api_management_name" {
  description = "Existing APIM instance with a system-assigned identity."
  type        = string
}

variable "api_management_resource_group_name" {
  description = "Resource group of the APIM instance."
  type        = string
}

variable "app_principal_id" {
  description = "Object ID of the RAG API's managed identity."
  type        = string
}

variable "ingestion_principal_id" {
  description = "Object ID of the identity that builds the search index (e.g. the CI deploy identity)."
  type        = string
  default     = null
}

locals {
  name = "larkspur-handbook"
  tags = {
    project = "azure-genai-platform"
    managed = "terraform"
  }
}

module "openai" {
  source = "../../modules/openai-service"

  name                       = "${local.name}-aoai"
  resource_group_name        = var.resource_group_name
  location                   = var.location
  log_analytics_workspace_id = var.log_analytics_workspace_id
  deployments = {
    chat = {
      model_name    = "gpt-4.1-mini"
      model_version = "2025-04-14"
      capacity      = 50
    }
    embeddings = {
      model_name    = "text-embedding-3-large"
      model_version = "1"
      capacity      = 50
    }
  }
  private_endpoint = {
    subnet_id            = var.private_endpoint_subnet_id
    private_dns_zone_ids = [var.openai_private_dns_zone_id]
  }
  tags = local.tags
}

module "search" {
  source = "../../modules/ai-search"

  name                       = "${local.name}-search"
  resource_group_name        = var.resource_group_name
  location                   = var.location
  log_analytics_workspace_id = var.log_analytics_workspace_id
  private_endpoint = {
    subnet_id            = var.private_endpoint_subnet_id
    private_dns_zone_ids = [var.search_private_dns_zone_id]
  }
  # Azure OpenAI has public access off, so the vectorizer reaches it privately.
  shared_private_links = {
    aoai = {
      target_resource_id = module.openai.id
      subresource_name   = "openai_account"
    }
  }
  tags = local.tags
}

module "gateway" {
  source = "../../modules/apim-ai-gateway"

  api_management_name = var.api_management_name
  resource_group_name = var.api_management_resource_group_name
  openai_endpoint     = module.openai.endpoint
  openai_account_id   = module.openai.id
  cloud               = var.cloud
  teams = {
    hr-assistant = { tokens_per_minute = 20000, monthly_token_quota = 50000000 }
    it-helpdesk  = { tokens_per_minute = 10000 }
  }
}

module "access" {
  source = "../../modules/rag-app-access"

  app_principal_id            = var.app_principal_id
  openai_account_id           = module.openai.id
  search_service_id           = module.search.id
  search_service_principal_id = module.search.principal_id
  ingestion_principal_id      = var.ingestion_principal_id
}

# Everything the app needs, in the env var names it reads (see app/README.md).
# RAG_AZURE_OPENAI_API_KEY is the team's APIM subscription key: load it from Key Vault.
output "app_environment" {
  description = "Environment variables for the RAG API container."
  value = {
    RAG_PROVIDER                     = "azure"
    RAG_AZURE_CLOUD                  = var.cloud
    RAG_AZURE_OPENAI_ENDPOINT        = module.gateway.gateway_url
    RAG_AZURE_OPENAI_DEPLOYMENT      = "chat"
    RAG_AZURE_SEARCH_ENDPOINT        = module.search.endpoint
    RAG_AZURE_SEARCH_INDEX           = "handbook"
    RAG_AZURE_EMBEDDING_DEPLOYMENT   = "embeddings"
    RAG_AZURE_OPENAI_RESOURCE_URI    = module.openai.endpoint
    RAG_AZURE_SEARCH_SEMANTIC_CONFIG = "default"
  }
}

output "pending_approvals" {
  description = "Shared private links to approve on the Azure OpenAI account (Networking > Private endpoint connections)."
  value       = module.search.shared_private_link_ids
}
