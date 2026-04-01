variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
}

variable "backend_port" {
  description = "Port the backend service listens on"
  type        = number
  default     = 8080
}

variable "domain_name" {
  description = "Domain name for managed SSL certificate (empty string disables HTTPS)"
  type        = string
  default     = ""
}

variable "serving_sa_email" {
  description = "Service account email for the prediction serving endpoint"
  type        = string
}
