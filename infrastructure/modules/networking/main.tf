# ============================================================================
# Meridian Networking Module
# VPC, Subnets, VPC Service Controls
# Competencies: Infrastructure & Network Security, Compliance & Governance
# ============================================================================

# ---- VPC Network ----

resource "google_compute_network" "meridian" {
  name                    = "meridian-vpc-${var.environment}"
  project                 = var.project_id
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
}

resource "google_compute_subnetwork" "meridian" {
  name          = "meridian-subnet-${var.environment}"
  project       = var.project_id
  region        = var.region
  network       = google_compute_network.meridian.id
  ip_cidr_range = "10.0.0.0/24"

  # Enable Private Google Access for Vertex AI and BigQuery
  private_ip_google_access = true

  log_config {
    aggregation_interval = "INTERVAL_5_SEC"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }
}

# ---- Firewall Rules ----

# Deny all ingress by default
resource "google_compute_firewall" "deny_all_ingress" {
  name    = "meridian-deny-all-ingress-${var.environment}"
  project = var.project_id
  network = google_compute_network.meridian.id

  direction = "INGRESS"
  priority  = 65534

  deny {
    protocol = "all"
  }

  source_ranges = ["0.0.0.0/0"]
}

# Allow internal communication within subnet
resource "google_compute_firewall" "allow_internal" {
  name    = "meridian-allow-internal-${var.environment}"
  project = var.project_id
  network = google_compute_network.meridian.id

  direction = "INGRESS"
  priority  = 1000

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }
  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }
  allow {
    protocol = "icmp"
  }

  source_ranges = [google_compute_subnetwork.meridian.ip_cidr_range]
}

# ---- Cloud NAT (for outbound internet from private subnet) ----

resource "google_compute_router" "meridian" {
  name    = "meridian-router-${var.environment}"
  project = var.project_id
  region  = var.region
  network = google_compute_network.meridian.id
}

resource "google_compute_router_nat" "meridian" {
  name                               = "meridian-nat-${var.environment}"
  project                            = var.project_id
  region                             = var.region
  router                             = google_compute_router.meridian.name
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}
