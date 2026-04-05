# Root composition variables (dev environment).
# Values supplied via dev.tfvars: terraform apply -var-file=dev.tfvars

# ---- Core ----

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

variable "zone" {
  description = "GCP zone"
  type        = string
}

# ---- Feature flags ----

variable "enable_api" {
  description = "Deploy the api module (Global Load Balancer, Cloud Armor, Cloud Endpoints). Set false to save GLB cost."
  type        = bool
  default     = true
}

variable "enable_vertex" {
  description = "Deploy the vertex module (Feature Store, TensorBoard, Prediction Endpoint)."
  type        = bool
  default     = true
}

# ---- Security / KMS ----

variable "kms_key_rotation_period" {
  description = "KMS key rotation period in seconds"
  type        = string
  default     = "7776000s"
}

# ---- BigQuery ----

variable "bq_dataset_id" {
  description = "BigQuery dataset ID (suffixed with _<env> by the module)"
  type        = string
  default     = "meridian_student_data"
}

variable "bq_delete_contents_on_destroy" {
  description = "Delete all tables when destroying dataset (dev only)"
  type        = bool
  default     = false
}

# ---- GCS ----

variable "gcs_location" {
  description = "GCS bucket location (US, EU, or regional)"
  type        = string
  default     = "US"
}

variable "gcs_storage_class" {
  description = "Default GCS storage class"
  type        = string
  default     = "STANDARD"
}

variable "gcs_lifecycle_age_nearline" {
  description = "Days before transition to Nearline"
  type        = number
  default     = 30
}

variable "gcs_lifecycle_age_coldline" {
  description = "Days before transition to Coldline"
  type        = number
  default     = 90
}

variable "gcs_lifecycle_age_archive" {
  description = "Days before transition to Archive"
  type        = number
  default     = 365
}

# ---- Networking / VPC-SC ----

variable "vpc_sc_dry_run" {
  description = "Run VPC Service Controls in dry-run mode"
  type        = bool
  default     = true
}

variable "enable_vpc_sc" {
  description = "Enable VPC Service Controls (requires org-level Access Context Manager)"
  type        = bool
  default     = false
}

variable "organization_id" {
  description = "GCP organization ID for VPC Service Controls (required if enable_vpc_sc = true)"
  type        = string
  default     = ""
}

variable "access_level_members" {
  description = "List of members allowed through VPC Service Controls perimeter"
  type        = list( string )
  default     = []
}

# ---- Vertex AI ----

variable "vertex_region" {
  description = "Region for Vertex AI resources"
  type        = string
  default     = "us-central1"
}

variable "featurestore_online_nodes" {
  description = "Number of Feature Store online serving nodes"
  type        = number
  default     = 1
}

# ---- API / GLB ----

variable "api_domain_name" {
  description = "Domain name for managed SSL certificate (empty disables HTTPS)"
  type        = string
  default     = ""
}

variable "api_backend_port" {
  description = "Port the prediction backend listens on"
  type        = number
  default     = 8080
}

# ---- Pub/Sub ----

variable "pubsub_message_retention" {
  description = "Pub/Sub topic message retention duration"
  type        = string
  default     = "604800s"
}

# ---- Monitoring ----

variable "monitoring_notification_email" {
  description = "Email address for alert notifications"
  type        = string
}

variable "monitoring_drift_threshold" {
  description = "Model drift score threshold that triggers an alert"
  type        = number
  default     = 0.1
}

variable "monitoring_error_rate_threshold" {
  description = "5xx error rate threshold (fraction) that triggers an alert"
  type        = number
  default     = 0.01
}
