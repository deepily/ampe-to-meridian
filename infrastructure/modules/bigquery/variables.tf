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
}

variable "dataset_id" {
  description = "BigQuery dataset ID"
  type        = string
  default     = "meridian_student_data"
}

variable "kms_bigquery_key_id" {
  description = "Cloud KMS key ID for BigQuery CMEK"
  type        = string
}

variable "delete_contents_on_destroy" {
  description = "Delete all tables when destroying dataset (dev only)"
  type        = bool
  default     = false
}
