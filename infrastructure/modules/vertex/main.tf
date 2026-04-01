# ============================================================================
# Meridian Vertex AI Module
# Feature Store, TensorBoard, Prediction Endpoint
# Competencies: ML Pipeline Architecture, Feature Engineering,
#               Model Serving & Monitoring
# ============================================================================

# ---- Feature Store ----

resource "google_vertex_ai_featurestore" "meridian" {
  provider = google-beta
  project  = var.project_id
  region   = var.region

  name = "meridian_features_${var.environment}"

  online_serving_config {
    fixed_node_count = var.featurestore_online_nodes
  }

  force_destroy = ( var.environment == "dev" )

  labels = {
    environment = var.environment
    project     = "meridian"
  }
}

# ---- Entity Types ----

resource "google_vertex_ai_featurestore_entitytype" "student" {
  provider     = google-beta
  featurestore = google_vertex_ai_featurestore.meridian.id
  name         = "student"

  monitoring_config {
    snapshot_analysis {
      disabled = ( var.environment == "dev" )
    }
  }
}

resource "google_vertex_ai_featurestore_entitytype" "course" {
  provider     = google-beta
  featurestore = google_vertex_ai_featurestore.meridian.id
  name         = "course"

  monitoring_config {
    snapshot_analysis {
      disabled = ( var.environment == "dev" )
    }
  }
}

# ---- TensorBoard ----

resource "google_vertex_ai_tensorboard" "meridian" {
  provider     = google-beta
  project      = var.project_id
  region       = var.region
  display_name = "Meridian Training (${var.environment})"

  labels = {
    environment = var.environment
    project     = "meridian"
  }
}

# ---- Prediction Endpoint ----

resource "google_vertex_ai_endpoint" "prediction" {
  provider     = google-beta
  project      = var.project_id
  location     = var.region
  name         = "meridian-prediction-${var.environment}"
  display_name = "Meridian Prediction (${var.environment})"
  network      = var.vpc_id != "" ? var.vpc_id : null

  labels = {
    environment = var.environment
    project     = "meridian"
  }
}
