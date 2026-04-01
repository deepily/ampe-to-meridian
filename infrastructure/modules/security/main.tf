# ============================================================================
# Meridian Security Module
# Cloud KMS, Secret Manager, IAM Service Accounts, Cloud DLP Templates
# Competencies: Data Protection & Privacy, Authentication & Authorization,
#               Compliance & Governance
# ============================================================================

# ---- Cloud KMS ----

resource "google_kms_key_ring" "meridian" {
  name     = "meridian-${var.environment}"
  location = var.region
  project  = var.project_id
}

resource "google_kms_crypto_key" "bigquery" {
  name            = "meridian-bq-${var.environment}"
  key_ring        = google_kms_key_ring.meridian.id
  rotation_period = var.kms_key_rotation_period
  purpose         = "ENCRYPT_DECRYPT"

  lifecycle {
    prevent_destroy = false # Allow destroy in dev; set true in prod
  }
}

resource "google_kms_crypto_key" "gcs" {
  name            = "meridian-gcs-${var.environment}"
  key_ring        = google_kms_key_ring.meridian.id
  rotation_period = var.kms_key_rotation_period
  purpose         = "ENCRYPT_DECRYPT"

  lifecycle {
    prevent_destroy = false
  }
}

# ---- IAM Service Accounts ----

# Pipeline service account -- runs Vertex AI Pipelines
resource "google_service_account" "pipeline" {
  account_id   = "meridian-pipeline-${var.environment}"
  display_name = "Meridian Pipeline SA (${var.environment})"
  project      = var.project_id
}

# Serving service account -- runs prediction endpoint
resource "google_service_account" "serving" {
  account_id   = "meridian-serving-${var.environment}"
  display_name = "Meridian Serving SA (${var.environment})"
  project      = var.project_id
}

# Monitoring service account -- Cloud Functions for drift alerts
resource "google_service_account" "monitoring" {
  account_id   = "meridian-monitor-${var.environment}"
  display_name = "Meridian Monitoring SA (${var.environment})"
  project      = var.project_id
}

# ---- Pipeline SA Roles (least privilege) ----

locals {
  pipeline_roles = [
    "roles/aiplatform.user",
    "roles/bigquery.dataEditor",
    "roles/bigquery.jobUser",
    "roles/storage.objectAdmin",
    "roles/dlp.user",
    "roles/secretmanager.secretAccessor",
    "roles/logging.logWriter",
    "roles/cloudtrace.agent",
    "roles/monitoring.metricWriter",
  ]

  serving_roles = [
    "roles/aiplatform.user",
    "roles/bigquery.dataViewer",
    "roles/storage.objectViewer",
    "roles/secretmanager.secretAccessor",
    "roles/logging.logWriter",
    "roles/redis.editor",
  ]

  monitoring_roles = [
    "roles/aiplatform.viewer",
    "roles/pubsub.subscriber",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
  ]
}

resource "google_project_iam_member" "pipeline" {
  for_each = toset( local.pipeline_roles )

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_project_iam_member" "serving" {
  for_each = toset( local.serving_roles )

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.serving.email}"
}

resource "google_project_iam_member" "monitoring" {
  for_each = toset( local.monitoring_roles )

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.monitoring.email}"
}

# ---- Grant KMS access to pipeline SA ----

resource "google_kms_crypto_key_iam_member" "pipeline_bq_key" {
  crypto_key_id = google_kms_crypto_key.bigquery.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_kms_crypto_key_iam_member" "pipeline_gcs_key" {
  crypto_key_id = google_kms_crypto_key.gcs.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${google_service_account.pipeline.email}"
}

# ---- Cloud DLP Inspect Template ----

resource "google_data_loss_prevention_inspect_template" "ferpa_pii" {
  parent       = "projects/${var.project_id}/locations/${var.region}"
  display_name = "Meridian FERPA PII Detection"
  description  = "Detects PII types relevant to FERPA compliance in student records"

  inspect_config {
    info_types {
      name = "PERSON_NAME"
    }
    info_types {
      name = "EMAIL_ADDRESS"
    }
    info_types {
      name = "US_SOCIAL_SECURITY_NUMBER"
    }
    info_types {
      name = "PHONE_NUMBER"
    }
    info_types {
      name = "DATE_OF_BIRTH"
    }

    min_likelihood = "POSSIBLE"

    limits {
      max_findings_per_request = 1000
    }
  }
}

# ---- Cloud DLP De-identify Template ----

resource "google_data_loss_prevention_deidentify_template" "ferpa_redact" {
  parent       = "projects/${var.project_id}/locations/${var.region}"
  display_name = "Meridian FERPA PII De-identification"
  description  = "Replaces detected PII with surrogate tokens for model training"

  deidentify_config {
    info_type_transformations {
      transformations {
        primitive_transformation {
          replace_with_info_type_config {}
        }
      }
    }
  }
}
