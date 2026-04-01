# ============================================================================
# Meridian Storage Module
# GCS Buckets with CMEK encryption and lifecycle policies
# Competencies: Data Protection & Privacy, Resource Efficiency
# ============================================================================

# ---- Training Data Bucket ----

resource "google_storage_bucket" "training_data" {
  name          = "meridian-training-data-${var.environment}-${var.project_id}"
  project       = var.project_id
  location      = var.location
  storage_class = var.storage_class

  uniform_bucket_level_access = true
  force_destroy               = true # Dev only; remove for prod

  encryption {
    default_kms_key_name = var.kms_gcs_key_id
  }

  versioning {
    enabled = true
  }
}

# ---- Pipeline Artifacts Bucket (models, features, snapshots) ----

resource "google_storage_bucket" "pipeline_artifacts" {
  name          = "meridian-artifacts-${var.environment}-${var.project_id}"
  project       = var.project_id
  location      = var.location
  storage_class = var.storage_class

  uniform_bucket_level_access = true
  force_destroy               = true

  encryption {
    default_kms_key_name = var.kms_gcs_key_id
  }

  versioning {
    enabled = true
  }

  # Lifecycle: Standard -> Nearline -> Coldline -> Archive
  # Competency: Resource Efficiency (GCS lifecycle management)
  lifecycle_rule {
    condition {
      age = var.lifecycle_age_nearline
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  lifecycle_rule {
    condition {
      age = var.lifecycle_age_coldline
    }
    action {
      type          = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }

  lifecycle_rule {
    condition {
      age = var.lifecycle_age_archive
    }
    action {
      type          = "SetStorageClass"
      storage_class = "ARCHIVE"
    }
  }
}

# ---- Terraform State Bucket ----

resource "google_storage_bucket" "tfstate" {
  name          = "meridian-tfstate-${var.environment}-${var.project_id}"
  project       = var.project_id
  location      = var.location
  storage_class = "STANDARD"

  uniform_bucket_level_access = true
  force_destroy               = false # Never destroy state bucket

  versioning {
    enabled = true
  }
}
