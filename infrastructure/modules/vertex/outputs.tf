output "featurestore_id" {
  description = "Vertex AI Feature Store ID"
  value       = google_vertex_ai_featurestore.meridian.id
}

output "student_entity_type_id" {
  description = "Student entity type ID in Feature Store"
  value       = google_vertex_ai_featurestore_entitytype.student.id
}

output "course_entity_type_id" {
  description = "Course entity type ID in Feature Store"
  value       = google_vertex_ai_featurestore_entitytype.course.id
}

output "tensorboard_id" {
  description = "Vertex AI TensorBoard instance ID"
  value       = google_vertex_ai_tensorboard.meridian.id
}

output "prediction_endpoint_id" {
  description = "Vertex AI Prediction endpoint ID"
  value       = google_vertex_ai_endpoint.prediction.id
}

output "prediction_endpoint_name" {
  description = "Vertex AI Prediction endpoint resource name"
  value       = google_vertex_ai_endpoint.prediction.name
}
