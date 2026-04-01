# ============================================================================
# Meridian Pub/Sub Module
# Pub/Sub Topics, Subscriptions, and Cloud Functions for drift alerting
# and retraining triggers
# Competencies: Event-Driven Architecture, MLOps Automation,
#               Model Monitoring & Retraining
# ============================================================================

# ---- Pub/Sub Topics ----

resource "google_pubsub_topic" "drift_alerts" {
  name    = "meridian-drift-alerts-${var.environment}"
  project = var.project_id

  message_retention_duration = var.message_retention_duration

  labels = {
    environment = var.environment
    component   = "monitoring"
    managed_by  = "terraform"
  }
}

resource "google_pubsub_topic" "retrain_trigger" {
  name    = "meridian-retrain-trigger-${var.environment}"
  project = var.project_id

  message_retention_duration = var.message_retention_duration

  labels = {
    environment = var.environment
    component   = "retraining"
    managed_by  = "terraform"
  }
}

# ---- Pub/Sub Subscriptions ----

resource "google_pubsub_subscription" "drift_alerts" {
  name    = "meridian-drift-alerts-sub-${var.environment}"
  project = var.project_id
  topic   = google_pubsub_topic.drift_alerts.id

  ack_deadline_seconds       = 60
  message_retention_duration = "604800s" # 7 days

  expiration_policy {
    ttl = "" # Never expires
  }

  labels = {
    environment = var.environment
    component   = "monitoring"
    managed_by  = "terraform"
  }
}

resource "google_pubsub_subscription" "retrain_trigger" {
  name    = "meridian-retrain-trigger-sub-${var.environment}"
  project = var.project_id
  topic   = google_pubsub_topic.retrain_trigger.id

  ack_deadline_seconds       = 120
  message_retention_duration = "604800s" # 7 days

  expiration_policy {
    ttl = "" # Never expires
  }

  labels = {
    environment = var.environment
    component   = "retraining"
    managed_by  = "terraform"
  }
}

# ---- Cloud Function Source Archives ----

data "archive_file" "drift_alert_function" {
  type        = "zip"
  source_dir  = "${path.module}/../../../src/pipeline/triggers/drift_alert_function"
  output_path = "${path.module}/tmp/drift_alert_function.zip"
}

data "archive_file" "retrain_function" {
  type        = "zip"
  source_dir  = "${path.module}/../../../src/pipeline/triggers/retrain_function"
  output_path = "${path.module}/tmp/retrain_function.zip"
}

resource "google_storage_bucket_object" "drift_function_source" {
  name   = "cloud-functions/drift-alert-${data.archive_file.drift_alert_function.output_md5}.zip"
  bucket = var.source_bucket
  source = data.archive_file.drift_alert_function.output_path
}

resource "google_storage_bucket_object" "retrain_function_source" {
  name   = "cloud-functions/retrain-${data.archive_file.retrain_function.output_md5}.zip"
  bucket = var.source_bucket
  source = data.archive_file.retrain_function.output_path
}

# ---- Cloud Functions (2nd Gen) ----

resource "google_cloudfunctions2_function" "drift_alert" {
  name     = "meridian-drift-alert-${var.environment}"
  location = var.region
  project  = var.project_id

  build_config {
    runtime     = "python311"
    entry_point = "handle_drift_alert"

    source {
      storage_source {
        bucket = var.source_bucket
        object = google_storage_bucket_object.drift_function_source.name
      }
    }
  }

  service_config {
    available_memory   = var.function_memory
    timeout_seconds    = var.function_timeout
    service_account_email = var.monitoring_sa_email

    environment_variables = {
      GCP_PROJECT_ID = var.project_id
      VERTEX_REGION  = var.region
    }
  }

  event_trigger {
    trigger_region = var.region
    event_type     = "google.cloud.pubsub.topic.v1.messagePublished"
    pubsub_topic   = google_pubsub_topic.drift_alerts.id
    retry_policy   = "RETRY_POLICY_RETRY"
  }

  labels = {
    environment = var.environment
    component   = "monitoring"
    managed_by  = "terraform"
  }
}

resource "google_cloudfunctions2_function" "retrain" {
  name     = "meridian-retrain-${var.environment}"
  location = var.region
  project  = var.project_id

  build_config {
    runtime     = "python311"
    entry_point = "trigger_retrain"

    source {
      storage_source {
        bucket = var.source_bucket
        object = google_storage_bucket_object.retrain_function_source.name
      }
    }
  }

  service_config {
    available_memory   = var.function_memory
    timeout_seconds    = var.function_timeout
    service_account_email = var.pipeline_sa_email

    environment_variables = {
      GCP_PROJECT_ID = var.project_id
      VERTEX_REGION  = var.region
    }
  }

  event_trigger {
    trigger_region = var.region
    event_type     = "google.cloud.pubsub.topic.v1.messagePublished"
    pubsub_topic   = google_pubsub_topic.retrain_trigger.id
    retry_policy   = "RETRY_POLICY_RETRY"
  }

  labels = {
    environment = var.environment
    component   = "retraining"
    managed_by  = "terraform"
  }
}
