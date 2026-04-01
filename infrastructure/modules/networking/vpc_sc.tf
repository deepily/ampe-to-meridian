# ============================================================================
# VPC Service Controls
# Creates a security perimeter around Vertex AI, BigQuery, GCS, KMS
# Competencies: Infrastructure & Network Security, Compliance & Governance,
#               Data Protection & Privacy
# ============================================================================

# Note: VPC Service Controls require an Access Context Manager policy
# at the organization level. This resource assumes the policy exists.
# In a dev environment, the perimeter starts in dry-run mode.

# ---- Access Context Manager Policy ----
# This data source retrieves the org-level access policy.
# If no org policy exists, comment out the vpc_sc resources.

# data "google_access_context_manager_access_policy" "org_policy" {
#   parent = "organizations/REPLACE_WITH_ORG_ID"
# }

# ---- Access Level (developer identity) ----

# resource "google_access_context_manager_access_level" "meridian_dev" {
#   parent = "accessPolicies/${data.google_access_context_manager_access_policy.org_policy.name}"
#   name   = "accessPolicies/${data.google_access_context_manager_access_policy.org_policy.name}/accessLevels/meridian_dev_${var.environment}"
#   title  = "Meridian Developer Access (${var.environment})"
#
#   basic {
#     conditions {
#       members = var.access_level_members
#     }
#   }
# }

# ---- Service Perimeter ----

# resource "google_access_context_manager_service_perimeter" "meridian" {
#   parent = "accessPolicies/${data.google_access_context_manager_access_policy.org_policy.name}"
#   name   = "accessPolicies/${data.google_access_context_manager_access_policy.org_policy.name}/servicePerimeters/meridian_${var.environment}"
#   title  = "Meridian ML Pipeline Perimeter (${var.environment})"
#
#   # Use dry-run in dev, enforced in prod
#   use_explicit_dry_run_spec = var.vpc_sc_dry_run
#
#   status {
#     restricted_services = [
#       "aiplatform.googleapis.com",
#       "bigquery.googleapis.com",
#       "storage.googleapis.com",
#       "cloudkms.googleapis.com",
#       "dlp.googleapis.com",
#       "secretmanager.googleapis.com",
#     ]
#
#     resources = [
#       "projects/${var.project_id}",
#     ]
#
#     access_levels = [
#       google_access_context_manager_access_level.meridian_dev.name,
#     ]
#   }
# }

# Note: VPC-SC resources are commented out by default because they require
# organization-level permissions. Uncomment and configure when deploying
# to an organization with Access Context Manager enabled.
#
# For FDE demonstration purposes, the Terraform code IS the artifact --
# it shows the correct resource definitions, IAM bindings, and service
# perimeter configuration even when not actively deployed.
