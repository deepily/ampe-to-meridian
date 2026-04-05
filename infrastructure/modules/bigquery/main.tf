# ============================================================================
# Meridian BigQuery Module
# Dataset, tables with CMEK, partitioning, and clustering
# Competencies: Resource Efficiency (partitioning/clustering),
#               Data Protection & Privacy (CMEK)
# ============================================================================

# ---- Dataset ----

resource "google_bigquery_dataset" "student_data" {
  dataset_id    = "${var.dataset_id}_${var.environment}"
  project       = var.project_id
  location      = var.region
  friendly_name = "Meridian Student Data (${var.environment})"
  description   = "Synthetic student retention data for Meridian ML pipeline"

  default_encryption_configuration {
    kms_key_name = var.kms_bigquery_key_id
  }

  delete_contents_on_destroy = var.delete_contents_on_destroy

  labels = {
    environment = var.environment
    project     = "meridian"
    domain      = "student-retention"
  }

  # Enable data access audit logging
  # Competency: Compliance & Governance
}

# ---- Table: student_demographics ----

resource "google_bigquery_table" "student_demographics" {
  dataset_id          = google_bigquery_dataset.student_data.dataset_id
  table_id            = "student_demographics"
  project             = var.project_id
  deletion_protection = false

  schema = file( "${path.module}/schemas/student_demographics.json" )

  labels = {
    pii_level = "high"
    table     = "demographics"
  }

  # Tables inherit CMEK from the dataset's default_encryption_configuration.
  # Ignore table-level encryption drift.
  lifecycle {
    ignore_changes = [encryption_configuration]
  }
}

# ---- Table: academic_records ----

resource "google_bigquery_table" "academic_records" {
  dataset_id          = google_bigquery_dataset.student_data.dataset_id
  table_id            = "academic_records"
  project             = var.project_id
  deletion_protection = false

  schema = file( "${path.module}/schemas/academic_records.json" )

  # Partition by term for efficient querying
  # Competency: Resource Efficiency
  range_partitioning {
    field = "term_code"
    range {
      start    = 201900
      end      = 202300
      interval = 100
    }
  }

  # Cluster by campus and major for common query patterns
  clustering = ["campus", "major"]

  labels = {
    pii_level = "low"
    table     = "academics"
  }

  lifecycle {
    ignore_changes = [encryption_configuration]
  }
}

# ---- Table: financial_aid ----

resource "google_bigquery_table" "financial_aid" {
  dataset_id          = google_bigquery_dataset.student_data.dataset_id
  table_id            = "financial_aid"
  project             = var.project_id
  deletion_protection = false

  schema = file( "${path.module}/schemas/financial_aid.json" )

  labels = {
    pii_level = "medium"
    table     = "financial"
  }

  lifecycle {
    ignore_changes = [encryption_configuration]
  }
}

# ---- Table: enrollment_events ----

resource "google_bigquery_table" "enrollment_events" {
  dataset_id          = google_bigquery_dataset.student_data.dataset_id
  table_id            = "enrollment_events"
  project             = var.project_id
  deletion_protection = false

  schema = file( "${path.module}/schemas/enrollment_events.json" )

  # Partition by event date
  time_partitioning {
    type  = "MONTH"
    field = "event_date"
  }

  clustering = ["event_type", "enrollment_status"]

  labels = {
    pii_level = "low"
    table     = "enrollment"
    target    = "second_year_ret_flag"
  }

  lifecycle {
    ignore_changes = [encryption_configuration]
  }
}

# ---- Prediction Logging Table ----
# Used by Model Monitoring to log predictions for drift detection
# Competency: Observability, Failure & Recovery Testing

resource "google_bigquery_table" "prediction_log" {
  dataset_id          = google_bigquery_dataset.student_data.dataset_id
  table_id            = "prediction_log"
  project             = var.project_id
  deletion_protection = false

  schema = file( "${path.module}/schemas/prediction_log.json" )

  time_partitioning {
    type  = "DAY"
    field = "prediction_timestamp"
  }

  labels = {
    pii_level = "low"
    table     = "predictions"
  }

  lifecycle {
    ignore_changes = [encryption_configuration]
  }
}
