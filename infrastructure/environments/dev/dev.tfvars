# Meridian Dev Environment
# Usage: terraform apply -var-file=dev.tfvars

# ---- Core ----
environment = "dev"
project_id  = "ampe-to-meridian"
region      = "us-central1"
zone        = "us-central1-a"

# ---- Feature flags ----
enable_api    = true # GLB, Cloud Armor (~$18/mo). Flip false to save cost.
enable_vertex = true # Feature Store, TensorBoard, Endpoint (~$5-10/mo).

# ---- KMS ----
kms_key_rotation_period = "7776000s" # 90 days

# ---- BigQuery ----
bq_dataset_id                 = "meridian_student_data"
bq_delete_contents_on_destroy = true

# ---- GCS ----
gcs_location               = "us-central1" # Regional to match KMS key ring (CMEK requires matching regions)
gcs_storage_class          = "STANDARD"
gcs_lifecycle_age_nearline = 30
gcs_lifecycle_age_coldline = 90
gcs_lifecycle_age_archive  = 365

# ---- Networking / VPC-SC ----
vpc_sc_dry_run  = true  # dry-run until org-level perms available
enable_vpc_sc   = false # keep disabled in dev
organization_id = ""

# ---- Vertex AI ----
vertex_region             = "us-central1"
featurestore_online_nodes = 1

# ---- API / GLB ----
api_domain_name  = "" # No custom domain in dev (HTTP only)
api_backend_port = 8080

# ---- Pub/Sub ----
pubsub_message_retention = "604800s" # 7 days

# ---- Monitoring ----
monitoring_notification_email   = "admin@rickruiz.altostrat.com"
monitoring_drift_threshold      = 0.1
monitoring_error_rate_threshold = 0.01
