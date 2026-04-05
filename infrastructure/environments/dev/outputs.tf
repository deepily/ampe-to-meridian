# Root composition outputs.
# Surface identifiers needed by scripts, CI, or humans post-apply.

output "project_id" {
  description = "GCP project ID"
  value       = var.project_id
}

output "tfstate_bucket" {
  description = "GCS bucket holding Terraform state"
  value       = module.storage.tfstate_bucket
}

output "training_data_bucket" {
  description = "GCS bucket for training data"
  value       = module.storage.training_data_bucket
}

output "pipeline_artifacts_bucket" {
  description = "GCS bucket for pipeline artifacts (KFP outputs, models, pipeline JSON)"
  value       = module.storage.pipeline_artifacts_bucket
}

output "bq_dataset_id" {
  description = "BigQuery dataset ID"
  value       = module.bigquery.dataset_id
}

output "pipeline_sa_email" {
  description = "Pipeline service account email"
  value       = module.security.pipeline_sa_email
}

output "serving_sa_email" {
  description = "Serving service account email"
  value       = module.security.serving_sa_email
}

output "monitoring_sa_email" {
  description = "Monitoring service account email"
  value       = module.security.monitoring_sa_email
}

output "dlp_inspect_template" {
  description = "Cloud DLP inspect template name"
  value       = module.security.dlp_inspect_template_name
}

output "dlp_deidentify_template" {
  description = "Cloud DLP de-identify template name"
  value       = module.security.dlp_deidentify_template_name
}

output "vertex_endpoint_id" {
  description = "Vertex AI Prediction endpoint ID (when enable_vertex = true)"
  value       = var.enable_vertex ? module.vertex[0].prediction_endpoint_id : ""
}

output "vertex_featurestore_id" {
  description = "Vertex AI Feature Store ID (when enable_vertex = true)"
  value       = var.enable_vertex ? module.vertex[0].featurestore_id : ""
}

output "vertex_tensorboard_id" {
  description = "Vertex AI TensorBoard ID (when enable_vertex = true)"
  value       = var.enable_vertex ? module.vertex[0].tensorboard_id : ""
}

output "drift_alerts_topic" {
  description = "Pub/Sub topic for drift alerts"
  value       = module.pubsub.drift_alerts_topic_name
}

output "retrain_trigger_topic" {
  description = "Pub/Sub topic for retrain triggers"
  value       = module.pubsub.retrain_trigger_topic_name
}

output "api_lb_ip" {
  description = "Global Load Balancer IP (when enable_api = true)"
  value       = var.enable_api ? module.api[0].load_balancer_ip : ""
}

output "vpc_id" {
  description = "VPC network ID"
  value       = module.networking.vpc_id
}
