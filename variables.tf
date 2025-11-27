variable "kestra_url" {
    type        = string
    description = "Base URL of the Kestra instance"
    default     = "http://localhost:8080"
}

variable "kestra_username" {
    type        = string
    description = "Basic auth username"
    default     = null
}

variable "kestra_password" {
    type        = string
    description = "Basic auth password"
    default     = null
    sensitive   = true
}

variable "kestra_api_token" {
    type        = string
    description = "Optional API token for Kestra EE"
    default     = null
    sensitive   = true
}

variable "tenant" {
    type        = string
    description = "Kestra tenant id"
    default     = "main"
}

variable "namespaces" {
    description = "List of namespaces to manage"
    type        = list(string)
}

variable "flows_by_namespace" {
    description = "Map of namespace -> list of flow IDs in that namespace"
    type        = map(list(string))
    default     = {}
}

variable "manage_users_and_groups" {
    description = "Whether to manage users, groups, roles, and IAM"
    type        = bool
    default     = true
}
