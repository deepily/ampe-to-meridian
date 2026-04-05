output "pipeline_dashboard_id" {
  description = "ID of the pipeline performance monitoring dashboard"
  value       = google_monitoring_dashboard.pipeline.id
}

output "model_dashboard_id" {
  description = "ID of the model health monitoring dashboard"
  value       = google_monitoring_dashboard.model.id
}

output "endpoint_dashboard_id" {
  description = "ID of the endpoint performance monitoring dashboard"
  value       = google_monitoring_dashboard.endpoint.id
}

output "drift_alert_policy_id" {
  description = "ID of the model drift alert policy (empty when enable_metric_alerts = false)"
  value       = var.enable_metric_alerts ? google_monitoring_alert_policy.drift_threshold[0].id : ""
}

output "endpoint_error_policy_id" {
  description = "ID of the endpoint error rate alert policy (empty when enable_metric_alerts = false)"
  value       = var.enable_metric_alerts ? google_monitoring_alert_policy.endpoint_errors[0].id : ""
}

output "pipeline_failure_policy_id" {
  description = "ID of the pipeline failure alert policy (empty when enable_metric_alerts = false)"
  value       = var.enable_metric_alerts ? google_monitoring_alert_policy.pipeline_failure[0].id : ""
}

output "notification_channel_id" {
  description = "ID of the email notification channel"
  value       = google_monitoring_notification_channel.email.id
}
