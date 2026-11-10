variable "api_management_name" {
  description = "Existing API Management instance. It must have a system-assigned managed identity."
  type        = string
}

variable "resource_group_name" {
  description = "Resource group of the API Management instance."
  type        = string
}

variable "openai_endpoint" {
  description = "Azure OpenAI endpoint, e.g. https://<name>.openai.azure.com/ (module output openai-service.endpoint)."
  type        = string

  validation {
    condition     = startswith(var.openai_endpoint, "https://")
    error_message = "openai_endpoint must be an https:// URL."
  }
}

variable "openai_account_id" {
  description = "Azure OpenAI account resource ID. The gateway's identity is granted Cognitive Services OpenAI User on it."
  type        = string
}

variable "cloud" {
  description = "Azure cloud: public or usgovernment. Sets the token audience the gateway requests for Azure OpenAI."
  type        = string
  default     = "public"

  validation {
    condition     = contains(["public", "usgovernment"], var.cloud)
    error_message = "cloud must be public or usgovernment."
  }
}

variable "api_path" {
  description = "Gateway path prefix. Keep \"openai\" so the OpenAI SDK's Azure client works unchanged against the gateway."
  type        = string
  default     = "openai"
}

variable "teams" {
  description = "One APIM product + subscription per consuming team, each with its own token-per-minute limit and optional monthly token quota."
  type = map(object({
    tokens_per_minute   = number
    monthly_token_quota = optional(number)
  }))
  default = {}

  validation {
    condition     = alltrue([for k in keys(var.teams) : can(regex("^[a-z0-9][a-z0-9-]{0,62}$", k))])
    error_message = "Team keys must be lowercase letters, digits and hyphens (they become APIM product IDs)."
  }

  validation {
    condition     = alltrue([for t in values(var.teams) : t.tokens_per_minute > 0 && (t.monthly_token_quota == null ? true : t.monthly_token_quota > 0)])
    error_message = "tokens_per_minute and monthly_token_quota must be positive."
  }
}

variable "metric_namespace" {
  description = "Application Insights custom-metric namespace for token usage."
  type        = string
  default     = "genai-gateway"
}

variable "retry_count" {
  description = "Retries on 429/5xx from Azure OpenAI before the error is returned. The backend circuit breaker trips on sustained throttling."
  type        = number
  default     = 2

  validation {
    condition     = var.retry_count >= 0 && var.retry_count <= 5
    error_message = "retry_count must be between 0 and 5."
  }
}
