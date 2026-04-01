output "drift_alerts_topic_id" {
  description = "Drift alerts Pub/Sub topic ID"
  value       = google_pubsub_topic.drift_alerts.id
}

output "drift_alerts_topic_name" {
  description = "Drift alerts Pub/Sub topic name"
  value       = google_pubsub_topic.drift_alerts.name
}

output "retrain_trigger_topic_id" {
  description = "Retrain trigger Pub/Sub topic ID"
  value       = google_pubsub_topic.retrain_trigger.id
}

output "retrain_trigger_topic_name" {
  description = "Retrain trigger Pub/Sub topic name"
  value       = google_pubsub_topic.retrain_trigger.name
}

output "drift_function_url" {
  description = "URL of the drift alert Cloud Function"
  value       = google_cloudfunctions2_function.drift_alert.url
}

output "retrain_function_url" {
  description = "URL of the retrain Cloud Function"
  value       = google_cloudfunctions2_function.retrain.url
}
