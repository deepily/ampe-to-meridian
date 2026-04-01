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

variable "kms_key_rotation_period" {
  description = "KMS key rotation period in seconds (default 90 days)"
  type        = string
  default     = "7776000s"
}
