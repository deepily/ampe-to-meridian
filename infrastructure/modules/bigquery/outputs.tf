output "dataset_id" {
  description = "BigQuery dataset ID"
  value       = google_bigquery_dataset.student_data.dataset_id
}

output "student_demographics_table_id" {
  description = "student_demographics table full ID"
  value       = "${google_bigquery_dataset.student_data.dataset_id}.${google_bigquery_table.student_demographics.table_id}"
}

output "academic_records_table_id" {
  description = "academic_records table full ID"
  value       = "${google_bigquery_dataset.student_data.dataset_id}.${google_bigquery_table.academic_records.table_id}"
}

output "financial_aid_table_id" {
  description = "financial_aid table full ID"
  value       = "${google_bigquery_dataset.student_data.dataset_id}.${google_bigquery_table.financial_aid.table_id}"
}

output "enrollment_events_table_id" {
  description = "enrollment_events table full ID"
  value       = "${google_bigquery_dataset.student_data.dataset_id}.${google_bigquery_table.enrollment_events.table_id}"
}

output "prediction_log_table_id" {
  description = "prediction_log table full ID"
  value       = "${google_bigquery_dataset.student_data.dataset_id}.${google_bigquery_table.prediction_log.table_id}"
}
