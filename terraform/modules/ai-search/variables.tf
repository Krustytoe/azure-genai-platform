variable "name" {
  description = "Search service name (globally unique, becomes <name>.search.windows.net)."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{0,58}[a-z0-9]$", var.name)) && !can(regex("--", var.name))
    error_message = "name must be 2-60 lowercase letters, digits or single hyphens, starting and ending with a letter or digit."
  }
}

variable "resource_group_name" {
  description = "Resource group for the service and its private endpoint."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "sku" {
  description = "Pricing tier. basic is enough for a pilot; standard adds capacity and more indexes."
  type        = string
  default     = "standard"

  validation {
    condition     = contains(["basic", "standard", "standard2", "standard3", "storage_optimized_l1", "storage_optimized_l2"], var.sku)
    error_message = "sku must be basic, standard, standard2, standard3, storage_optimized_l1 or storage_optimized_l2 (free has no SLA, private endpoints or managed identity)."
  }
}

variable "replica_count" {
  description = "Replicas. 2 gives the read SLA, 3 gives read/write. Each replica is billed."
  type        = number
  default     = 2

  validation {
    condition     = var.replica_count >= 1 && var.replica_count <= 12
    error_message = "replica_count must be between 1 and 12."
  }
}

variable "partition_count" {
  description = "Partitions (storage and indexing throughput)."
  type        = number
  default     = 1

  validation {
    condition     = contains([1, 2, 3, 4, 6, 12], var.partition_count)
    error_message = "partition_count must be 1, 2, 3, 4, 6 or 12."
  }
}

variable "semantic_search_sku" {
  description = "Semantic ranker plan (free or standard). The RAG API uses reranker scores to decide whether a chunk is relevant. null disables it."
  type        = string
  default     = "standard"

  validation {
    condition     = var.semantic_search_sku == null ? true : contains(["free", "standard"], var.semantic_search_sku)
    error_message = "semantic_search_sku must be null, free or standard."
  }
}

variable "public_network_access_enabled" {
  description = "Allow access from public networks. Secure default false."
  type        = bool
  default     = false
}

variable "allowed_ips" {
  description = "Public IPs/CIDRs allowed when public access is enabled."
  type        = list(string)
  default     = []
}

variable "private_endpoint" {
  description = "Private endpoint placement. private_dns_zone_ids should contain privatelink.search.windows.net (privatelink.search.azure.us in Azure Government). null skips the endpoint."
  type = object({
    subnet_id            = string
    private_dns_zone_ids = list(string)
  })
  default = null
}

variable "shared_private_links" {
  description = "Outbound private links from the search service, e.g. to a private Azure OpenAI account for query-time vectorization ({ aoai = { target_resource_id = ..., subresource_name = \"openai_account\" } }). The target owner must approve each connection."
  type = map(object({
    target_resource_id = string
    subresource_name   = string
  }))
  default = {}
}

variable "log_analytics_workspace_id" {
  description = "Workspace for audit logs and metrics."
  type        = string
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default     = {}
}
