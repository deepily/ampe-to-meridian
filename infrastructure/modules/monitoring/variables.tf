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

variable "enable_metric_alerts" {
  description = "Create alert policies that reference metrics (drift, 5xx errors, pipeline failures). Disable on first deploy, enable after metrics have been emitted at least once."
  type        = bool
  default     = false
}
