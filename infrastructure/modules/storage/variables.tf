variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "location" {
  description = "GCS bucket location for data buckets (training_data, pipeline_artifacts). Must match KMS key ring region when CMEK is used."
  type        = string
  default     = "US"
}

variable "tfstate_location" {
  description = "GCS bucket location for the tfstate bucket (decoupled from data buckets because tfstate does not use CMEK)."
  type        = string
  default     = "US"
}

variable "storage_class" {
  description = "Default storage class"
  type        = string
  default     = "STANDARD"
}

variable "kms_gcs_key_id" {
  description = "Cloud KMS key ID for CMEK encryption on GCS buckets"
  type        = string
}

variable "lifecycle_age_nearline" {
  description = "Days before transition to Nearline"
  type        = number
  default     = 30
}

variable "lifecycle_age_coldline" {
  description = "Days before transition to Coldline"
  type        = number
  default     = 90
}

variable "lifecycle_age_archive" {
  description = "Days before transition to Archive"
  type        = number
  default     = 365
}
