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

variable "monitoring_sa_email" {
  description = "Service account email for the drift alert Cloud Function"
  type        = string
}

variable "pipeline_sa_email" {
  description = "Service account email for the retrain Cloud Function"
  type        = string
}

variable "source_bucket" {
  description = "GCS bucket name for Cloud Function source zip uploads"
  type        = string
}

variable "message_retention_duration" {
  description = "Pub/Sub topic message retention duration (default 7 days)"
  type        = string
  default     = "604800s"
}

variable "function_memory" {
  description = "Memory allocation for Cloud Functions"
  type        = string
  default     = "256M"
}

variable "function_timeout" {
  description = "Timeout in seconds for Cloud Functions"
  type        = number
  default     = 120
}
