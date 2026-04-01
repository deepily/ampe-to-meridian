output "training_data_bucket" {
  description = "Training data GCS bucket name"
  value       = google_storage_bucket.training_data.name
}

output "pipeline_artifacts_bucket" {
  description = "Pipeline artifacts GCS bucket name"
  value       = google_storage_bucket.pipeline_artifacts.name
}

output "tfstate_bucket" {
  description = "Terraform state GCS bucket name"
  value       = google_storage_bucket.tfstate.name
}
