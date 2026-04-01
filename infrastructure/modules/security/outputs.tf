output "kms_key_ring_id" {
  description = "KMS key ring ID"
  value       = google_kms_key_ring.meridian.id
}

output "kms_bigquery_key_id" {
  description = "KMS key ID for BigQuery CMEK"
  value       = google_kms_crypto_key.bigquery.id
}

output "kms_gcs_key_id" {
  description = "KMS key ID for GCS CMEK"
  value       = google_kms_crypto_key.gcs.id
}

output "pipeline_sa_email" {
  description = "Pipeline service account email"
  value       = google_service_account.pipeline.email
}

output "serving_sa_email" {
  description = "Serving service account email"
  value       = google_service_account.serving.email
}

output "monitoring_sa_email" {
  description = "Monitoring service account email"
  value       = google_service_account.monitoring.email
}

output "dlp_inspect_template_name" {
  description = "Cloud DLP inspect template resource name"
  value       = google_data_loss_prevention_inspect_template.ferpa_pii.name
}

output "dlp_deidentify_template_name" {
  description = "Cloud DLP de-identify template resource name"
  value       = google_data_loss_prevention_deidentify_template.ferpa_redact.name
}
