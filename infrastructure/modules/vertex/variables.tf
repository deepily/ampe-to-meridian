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

variable "pipeline_sa_email" {
  description = "Pipeline service account email for Vertex AI access"
  type        = string
}

variable "serving_sa_email" {
  description = "Serving service account email for prediction endpoint"
  type        = string
}

variable "featurestore_online_nodes" {
  description = "Number of online serving nodes for Feature Store"
  type        = number
  default     = 1
}

variable "vpc_id" {
  description = "VPC network ID for private endpoint peering (optional)"
  type        = string
  default     = ""
}
