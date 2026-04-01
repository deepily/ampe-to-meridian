variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string

  validation {
    condition     = contains( ["dev", "staging", "prod"], var.environment )
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

variable "notification_email" {
  description = "Email address for alert notifications"
  type        = string
}

variable "drift_threshold" {
  description = "Model drift score threshold that triggers an alert"
  type        = number
  default     = 0.1
}

variable "error_rate_threshold" {
  description = "5xx error rate threshold (fraction) that triggers an alert"
  type        = number
  default     = 0.01
}

variable "endpoint_url" {
  description = "Prediction endpoint URL for uptime checks (empty string disables the check)"
  type        = string
  default     = ""
}
