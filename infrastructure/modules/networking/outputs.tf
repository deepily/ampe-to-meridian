output "vpc_id" {
  description = "VPC network ID"
  value       = google_compute_network.meridian.id
}

output "vpc_name" {
  description = "VPC network name"
  value       = google_compute_network.meridian.name
}

output "subnet_id" {
  description = "Subnet ID"
  value       = google_compute_subnetwork.meridian.id
}

output "subnet_name" {
  description = "Subnet name"
  value       = google_compute_subnetwork.meridian.name
}
