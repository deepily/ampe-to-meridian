output "global_ip_address" {
  description = "Global static IP address resource ID"
  value       = google_compute_global_address.api.id
}

output "load_balancer_ip" {
  description = "Global static IP address value"
  value       = google_compute_global_address.api.address
}

output "cloud_armor_policy_id" {
  description = "Cloud Armor WAF security policy ID"
  value       = google_compute_security_policy.waf.id
}

output "health_check_id" {
  description = "Health check resource ID"
  value       = google_compute_health_check.api.id
}

output "backend_service_id" {
  description = "Backend service resource ID"
  value       = google_compute_backend_service.api.id
}

output "http_forwarding_rule_id" {
  description = "HTTP forwarding rule resource ID"
  value       = google_compute_global_forwarding_rule.http.id
}
