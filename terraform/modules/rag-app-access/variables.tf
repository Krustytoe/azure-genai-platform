variable "app_principal_id" {
  description = "Object ID of the RAG API's managed identity (Container Apps, AKS workload identity, App Service)."
  type        = string
}

variable "openai_account_id" {
  description = "Azure OpenAI account resource ID."
  type        = string
}

variable "search_service_id" {
  description = "AI Search service resource ID."
  type        = string
}

variable "grant_app_direct_openai" {
  description = "Let the app call Azure OpenAI directly. Set false when all traffic must go through the APIM gateway, so the gateway is the only path."
  type        = bool
  default     = false
}

variable "search_service_principal_id" {
  description = "Object ID of the search service's managed identity. Granted Azure OpenAI access so the index vectorizer can embed queries. null skips it."
  type        = string
  default     = null
}

variable "ingestion_principal_id" {
  description = "Object ID of the identity that builds the index (CI pipeline or a job). Gets index write/manage on search and embeddings on Azure OpenAI. null skips it."
  type        = string
  default     = null
}

variable "principal_type" {
  description = "Principal type for the app and ingestion identities. Setting it avoids failures from Entra ID replication delay on fresh identities."
  type        = string
  default     = "ServicePrincipal"

  validation {
    condition     = contains(["ServicePrincipal", "User", "Group"], var.principal_type)
    error_message = "principal_type must be ServicePrincipal, User or Group."
  }
}
