# Meridian Dev Environment
# Usage: terraform apply -var-file=dev.tfvars

environment = "dev"
project_id  = "ampe-to-meridian"
region      = "us-central1"
zone        = "us-central1-a"

# KMS
kms_key_rotation_period = "7776000s" # 90 days

# BigQuery
bq_dataset_id            = "meridian_student_data"
bq_delete_contents_on_destroy = true

# GCS
gcs_location             = "US"
gcs_storage_class        = "STANDARD"
gcs_lifecycle_age_nearline  = 30
gcs_lifecycle_age_coldline  = 90
gcs_lifecycle_age_archive   = 365

# VPC Service Controls
vpc_sc_dry_run = true # Start in dry-run, promote to enforced in Phase 5

# Vertex AI
vertex_region = "us-central1"

# Memorystore (Phase 4 -- comment out to save cost)
# memorystore_tier          = "BASIC"
# memorystore_memory_size_gb = 1
