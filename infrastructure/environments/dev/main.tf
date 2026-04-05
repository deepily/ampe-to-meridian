# ============================================================================
# Meridian Root Composition -- dev environment
# Wires 8 modules: security, networking, storage, bigquery, vertex, pubsub,
#                  monitoring, api
# Module order respects implicit dependencies:
#   security → { storage (KMS), bigquery (KMS), vertex (SAs), pubsub (SAs), api (SA) }
#   networking → vertex (VPC peering)
#   storage → pubsub (Cloud Function source bucket)
# ============================================================================

module "security" {
  source = "../../modules/security"

  project_id              = var.project_id
  region                  = var.region
  environment             = var.environment
  kms_key_rotation_period = var.kms_key_rotation_period
}

module "networking" {
  source = "../../modules/networking"

  project_id           = var.project_id
  region               = var.region
  environment          = var.environment
  vpc_sc_dry_run       = var.vpc_sc_dry_run
  enable_vpc_sc        = var.enable_vpc_sc
  organization_id      = var.organization_id
  access_level_members = var.access_level_members
}

module "storage" {
  source = "../../modules/storage"

  project_id             = var.project_id
  environment            = var.environment
  location               = var.gcs_location
  storage_class          = var.gcs_storage_class
  kms_gcs_key_id         = module.security.kms_gcs_key_id
  lifecycle_age_nearline = var.gcs_lifecycle_age_nearline
  lifecycle_age_coldline = var.gcs_lifecycle_age_coldline
  lifecycle_age_archive  = var.gcs_lifecycle_age_archive

  # Wait for GCS service agent KMS encrypter grant before creating CMEK buckets
  depends_on = [module.security]
}

module "bigquery" {
  source = "../../modules/bigquery"

  project_id                 = var.project_id
  region                     = var.region
  environment                = var.environment
  dataset_id                 = var.bq_dataset_id
  kms_bigquery_key_id        = module.security.kms_bigquery_key_id
  delete_contents_on_destroy = var.bq_delete_contents_on_destroy

  # Wait for BQ service agent KMS encrypter grant before creating CMEK dataset
  depends_on = [module.security]
}

module "vertex" {
  count  = var.enable_vertex ? 1 : 0
  source = "../../modules/vertex"

  project_id                = var.project_id
  region                    = var.vertex_region
  environment               = var.environment
  pipeline_sa_email         = module.security.pipeline_sa_email
  serving_sa_email          = module.security.serving_sa_email
  featurestore_online_nodes = var.featurestore_online_nodes
  # Public endpoint in dev. VPC peering needs the project NUMBER format
  # (projects/{number}/global/networks/{name}), not the self_link.
  vpc_id = ""
}

module "pubsub" {
  source = "../../modules/pubsub"

  project_id                 = var.project_id
  region                     = var.region
  environment                = var.environment
  monitoring_sa_email        = module.security.monitoring_sa_email
  pipeline_sa_email          = module.security.pipeline_sa_email
  source_bucket              = module.storage.pipeline_artifacts_bucket
  message_retention_duration = var.pubsub_message_retention
}

module "monitoring" {
  source = "../../modules/monitoring"

  project_id           = var.project_id
  region               = var.region
  environment          = var.environment
  notification_email   = var.monitoring_notification_email
  drift_threshold      = var.monitoring_drift_threshold
  error_rate_threshold = var.monitoring_error_rate_threshold
  endpoint_url         = ""
}

module "api" {
  count  = var.enable_api ? 1 : 0
  source = "../../modules/api"

  project_id       = var.project_id
  environment      = var.environment
  region           = var.region
  backend_port     = var.api_backend_port
  domain_name      = var.api_domain_name
  serving_sa_email = module.security.serving_sa_email
}
