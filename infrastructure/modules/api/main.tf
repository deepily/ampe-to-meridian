# ============================================================================
# Meridian API Module
# Global Load Balancer, Cloud Armor WAF, Prediction Endpoint Infrastructure
# Competencies: Infrastructure & Network Security, ML Model Deployment
# ============================================================================

# ---- Cloud Armor WAF Policy ----

resource "google_compute_security_policy" "waf" {
  name    = "meridian-waf-${var.environment}"
  project = var.project_id

  # Default rule: allow all traffic
  rule {
    action   = "allow"
    priority = 2147483647

    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }

    description = "Default allow rule"
  }

  # OWASP ModSecurity CRS: block SQLi and XSS
  rule {
    action   = "deny(403)"
    priority = 1000

    match {
      expr {
        expression = "evaluatePreconfiguredExpr('sqli-stable') || evaluatePreconfiguredExpr('xss-stable')"
      }
    }

    description = "Block SQL injection and XSS attacks (OWASP CRS)"
  }

  # Rate limiting: 100 requests per minute per IP
  rule {
    action   = "rate_based_ban"
    priority = 2000

    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }

    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"

      rate_limit_threshold {
        count        = 100
        interval_sec = 60
      }

      ban_duration_sec = 300
    }

    description = "Rate limit: 100 requests/min per IP"
  }

  adaptive_protection_config {
    layer_7_ddos_defense_config {
      enable = true
    }
  }
}

# ---- Static IP Address ----

resource "google_compute_global_address" "api" {
  name    = "meridian-api-${var.environment}"
  project = var.project_id
}

# ---- Health Check ----

resource "google_compute_health_check" "api" {
  name    = "meridian-api-health-${var.environment}"
  project = var.project_id

  check_interval_sec  = 10
  timeout_sec         = 5
  healthy_threshold   = 2
  unhealthy_threshold = 3

  http_health_check {
    port         = var.backend_port
    request_path = "/health"
  }
}

# ---- Backend Service ----

resource "google_compute_backend_service" "api" {
  name    = "meridian-api-backend-${var.environment}"
  project = var.project_id

  protocol                        = "HTTP"
  health_checks                   = [google_compute_health_check.api.id]
  connection_draining_timeout_sec = 300
  security_policy                 = google_compute_security_policy.waf.id

  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

# ---- URL Map ----

resource "google_compute_url_map" "api" {
  name    = "meridian-api-urlmap-${var.environment}"
  project = var.project_id

  default_service = google_compute_backend_service.api.id
}

# ---- Managed SSL Certificate (conditional: only if domain provided) ----

resource "google_compute_managed_ssl_certificate" "api" {
  count   = var.domain_name != "" ? 1 : 0
  name    = "meridian-api-cert-${var.environment}"
  project = var.project_id

  managed {
    domains = [var.domain_name]
  }
}

# ---- HTTPS Proxy (conditional: only if domain provided) ----

resource "google_compute_target_https_proxy" "api" {
  count   = var.domain_name != "" ? 1 : 0
  name    = "meridian-api-proxy-${var.environment}"
  project = var.project_id

  url_map          = google_compute_url_map.api.id
  ssl_certificates = [google_compute_managed_ssl_certificate.api[0].id]
}

# ---- HTTP Proxy (always available) ----

resource "google_compute_target_http_proxy" "api" {
  name    = "meridian-api-http-proxy-${var.environment}"
  project = var.project_id

  url_map = google_compute_url_map.api.id
}

# ---- HTTP Forwarding Rule ----

resource "google_compute_global_forwarding_rule" "http" {
  name    = "meridian-api-http-${var.environment}"
  project = var.project_id

  ip_address = google_compute_global_address.api.address
  port_range = "80"
  target     = google_compute_target_http_proxy.api.id
}

# ---- HTTPS Forwarding Rule (conditional: only if domain provided) ----

resource "google_compute_global_forwarding_rule" "https" {
  count   = var.domain_name != "" ? 1 : 0
  name    = "meridian-api-https-${var.environment}"
  project = var.project_id

  ip_address = google_compute_global_address.api.address
  port_range = "443"
  target     = google_compute_target_https_proxy.api[0].id
}
