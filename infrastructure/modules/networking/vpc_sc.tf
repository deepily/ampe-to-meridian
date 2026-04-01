# ============================================================================
# VPC Service Controls
# Creates a security perimeter around Vertex AI, BigQuery, GCS, KMS
# Competencies: Infrastructure & Network Security, Compliance & Governance,
#               Data Protection & Privacy
# ============================================================================

# Note: VPC Service Controls require an Access Context Manager policy
# at the organization level. Set enable_vpc_sc = true and provide
# organization_id to activate. In dev, the perimeter runs in dry-run mode.

# ---- Access Context Manager Policy ----

data "google_access_context_manager_access_policy" "org_policy" {
  count  = var.enable_vpc_sc ? 1 : 0
  parent = "organizations/${var.organization_id}"
}

# ---- Access Level (developer identity) ----

resource "google_access_context_manager_access_level" "meridian_dev" {
  count  = var.enable_vpc_sc ? 1 : 0
  parent = "accessPolicies/${data.google_access_context_manager_access_policy.org_policy[0].name}"
  name   = "accessPolicies/${data.google_access_context_manager_access_policy.org_policy[0].name}/accessLevels/meridian_dev_${var.environment}"
  title  = "Meridian Developer Access (${var.environment})"

  basic {
    conditions {
      members = var.access_level_members
    }
  }
}

# ---- Service Perimeter ----

resource "google_access_context_manager_service_perimeter" "meridian" {
  count  = var.enable_vpc_sc ? 1 : 0
  parent = "accessPolicies/${data.google_access_context_manager_access_policy.org_policy[0].name}"
  name   = "accessPolicies/${data.google_access_context_manager_access_policy.org_policy[0].name}/servicePerimeters/meridian_${var.environment}"
  title  = "Meridian ML Pipeline Perimeter (${var.environment})"

  # Use dry-run in dev, enforced in prod
  use_explicit_dry_run_spec = var.vpc_sc_dry_run

  status {
    restricted_services = [
      "aiplatform.googleapis.com",
      "bigquery.googleapis.com",
      "storage.googleapis.com",
      "cloudkms.googleapis.com",
      "dlp.googleapis.com",
      "secretmanager.googleapis.com",
    ]

    resources = [
      "projects/${var.project_id}",
    ]

    access_levels = [
      google_access_context_manager_access_level.meridian_dev[0].name,
    ]
  }
}
