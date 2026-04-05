# ============================================================================
# Meridian Monitoring Module
# Cloud Monitoring Dashboards, Alerting Policies, Uptime Checks
# Competencies: Observability & Incident Response, ML Pipeline Monitoring,
#               Model Performance Tracking
# ============================================================================

# ---- Notification Channel ----

resource "google_monitoring_notification_channel" "email" {
  project      = var.project_id
  display_name = "Meridian Alerts (${var.environment})"
  type         = "email"

  labels = {
    email_address = var.notification_email
  }
}

# ---- Alert Policy: Model Drift ----

resource "google_monitoring_alert_policy" "drift_threshold" {
  count        = var.enable_metric_alerts ? 1 : 0
  project      = var.project_id
  display_name = "Meridian Model Drift Alert (${var.environment})"
  combiner     = "OR"

  conditions {
    display_name = "Model drift score exceeds threshold"

    condition_threshold {
      filter          = "metric.type=\"custom.googleapis.com/meridian/model_drift_score\" AND resource.type=\"global\""
      comparison      = "COMPARISON_GT"
      threshold_value = var.drift_threshold
      duration        = "300s"

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  notification_channels = [
    google_monitoring_notification_channel.email.id
  ]

  documentation {
    content   = "Model drift score has exceeded ${var.drift_threshold}. Investigate feature distributions and consider retraining."
    mime_type = "text/markdown"
  }
}

# ---- Alert Policy: Endpoint Errors ----

resource "google_monitoring_alert_policy" "endpoint_errors" {
  count        = var.enable_metric_alerts ? 1 : 0
  project      = var.project_id
  display_name = "Meridian Endpoint Error Rate (${var.environment})"
  combiner     = "OR"

  conditions {
    display_name = "5xx error rate exceeds threshold"

    condition_threshold {
      filter          = "metric.type=\"compute.googleapis.com/https/request_count\" AND metric.labels.response_code_class=\"500\" AND resource.type=\"global\""
      comparison      = "COMPARISON_GT"
      threshold_value = var.error_rate_threshold
      duration        = "60s"

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = [
    google_monitoring_notification_channel.email.id
  ]

  documentation {
    content   = "Prediction endpoint 5xx error rate has exceeded ${var.error_rate_threshold}. Check endpoint logs and serving container health."
    mime_type = "text/markdown"
  }
}

# ---- Alert Policy: Pipeline Failure ----

resource "google_monitoring_alert_policy" "pipeline_failure" {
  count        = var.enable_metric_alerts ? 1 : 0
  project      = var.project_id
  display_name = "Meridian Pipeline Failure (${var.environment})"
  combiner     = "OR"

  conditions {
    display_name = "Pipeline job failure detected"

    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/meridian_pipeline_failure\" AND resource.type=\"global\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  notification_channels = [
    google_monitoring_notification_channel.email.id
  ]

  documentation {
    content   = "A Meridian pipeline job has failed. Check Vertex AI Pipelines console for details."
    mime_type = "text/markdown"
  }
}

# ---- Dashboard: Pipeline Performance ----

resource "google_monitoring_dashboard" "pipeline" {
  project        = var.project_id
  dashboard_json = jsonencode( {
    displayName = "Meridian Pipeline (${var.environment})"
    gridLayout = {
      columns = 3
      widgets = [
        {
          title = "Pipeline Stage Latencies"
          xyChart = {
            dataSets = [ {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"custom.googleapis.com/meridian/pipeline_stage_latency\" AND resource.type=\"global\""
                  aggregation = {
                    alignmentPeriod  = "300s"
                    perSeriesAligner = "ALIGN_PERCENTILE_99"
                  }
                }
              }
              plotType = "LINE"
            } ]
            timeshiftDuration = "0s"
          }
        },
        {
          title = "Data Volume (rows processed)"
          xyChart = {
            dataSets = [ {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"custom.googleapis.com/meridian/data_volume_rows\" AND resource.type=\"global\""
                  aggregation = {
                    alignmentPeriod  = "300s"
                    perSeriesAligner = "ALIGN_SUM"
                  }
                }
              }
              plotType = "STACKED_BAR"
            } ]
            timeshiftDuration = "0s"
          }
        },
        {
          title = "Pipeline Error Counts"
          xyChart = {
            dataSets = [ {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"custom.googleapis.com/meridian/pipeline_error_count\" AND resource.type=\"global\""
                  aggregation = {
                    alignmentPeriod  = "300s"
                    perSeriesAligner = "ALIGN_SUM"
                  }
                }
              }
              plotType = "STACKED_BAR"
            } ]
            timeshiftDuration = "0s"
          }
        }
      ]
    }
  } )
}

# ---- Dashboard: Model Health ----

resource "google_monitoring_dashboard" "model" {
  project        = var.project_id
  dashboard_json = jsonencode( {
    displayName = "Meridian Model Health (${var.environment})"
    gridLayout = {
      columns = 3
      widgets = [
        {
          title = "Model Drift Scores"
          xyChart = {
            dataSets = [ {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"custom.googleapis.com/meridian/model_drift_score\" AND resource.type=\"global\""
                  aggregation = {
                    alignmentPeriod  = "300s"
                    perSeriesAligner = "ALIGN_MEAN"
                  }
                }
              }
              plotType = "LINE"
            } ]
            timeshiftDuration = "0s"
          }
        },
        {
          title = "Prediction Distribution"
          xyChart = {
            dataSets = [ {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"custom.googleapis.com/meridian/prediction_distribution\" AND resource.type=\"global\""
                  aggregation = {
                    alignmentPeriod  = "300s"
                    perSeriesAligner = "ALIGN_MEAN"
                  }
                }
              }
              plotType = "HEATMAP"
            } ]
            timeshiftDuration = "0s"
          }
        },
        {
          title = "Feature Distributions"
          xyChart = {
            dataSets = [ {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"custom.googleapis.com/meridian/feature_distribution\" AND resource.type=\"global\""
                  aggregation = {
                    alignmentPeriod  = "300s"
                    perSeriesAligner = "ALIGN_MEAN"
                  }
                }
              }
              plotType = "LINE"
            } ]
            timeshiftDuration = "0s"
          }
        }
      ]
    }
  } )
}

# ---- Dashboard: Endpoint Performance ----

resource "google_monitoring_dashboard" "endpoint" {
  project        = var.project_id
  dashboard_json = jsonencode( {
    displayName = "Meridian Endpoint (${var.environment})"
    gridLayout = {
      columns = 2
      widgets = [
        {
          title = "Request Latency (p50 / p99)"
          xyChart = {
            dataSets = [ {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"custom.googleapis.com/meridian/endpoint_latency\" AND resource.type=\"global\""
                  aggregation = {
                    alignmentPeriod  = "60s"
                    perSeriesAligner = "ALIGN_PERCENTILE_99"
                  }
                }
              }
              plotType = "LINE"
            } ]
            timeshiftDuration = "0s"
          }
        },
        {
          title = "Error Rate (5xx)"
          xyChart = {
            dataSets = [ {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"compute.googleapis.com/https/request_count\" AND metric.labels.response_code_class=\"500\" AND resource.type=\"global\""
                  aggregation = {
                    alignmentPeriod  = "60s"
                    perSeriesAligner = "ALIGN_RATE"
                  }
                }
              }
              plotType = "LINE"
            } ]
            timeshiftDuration = "0s"
          }
        },
        {
          title = "Traffic Volume (requests/sec)"
          xyChart = {
            dataSets = [ {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"compute.googleapis.com/https/request_count\" AND resource.type=\"global\""
                  aggregation = {
                    alignmentPeriod  = "60s"
                    perSeriesAligner = "ALIGN_RATE"
                  }
                }
              }
              plotType = "LINE"
            } ]
            timeshiftDuration = "0s"
          }
        },
        {
          title = "Cache Hit Rate"
          xyChart = {
            dataSets = [ {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"custom.googleapis.com/meridian/cache_hit_rate\" AND resource.type=\"global\""
                  aggregation = {
                    alignmentPeriod  = "60s"
                    perSeriesAligner = "ALIGN_MEAN"
                  }
                }
              }
              plotType = "LINE"
            } ]
            timeshiftDuration = "0s"
          }
        }
      ]
    }
  } )
}

# ---- Uptime Check: Prediction Endpoint ----

resource "google_monitoring_uptime_check_config" "endpoint" {
  count        = var.endpoint_url != "" ? 1 : 0
  project      = var.project_id
  display_name = "Meridian Prediction Endpoint (${var.environment})"
  timeout      = "10s"
  period       = "300s"

  http_check {
    path         = "/health"
    port         = 443
    use_ssl      = true
    validate_ssl = true
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = var.endpoint_url
    }
  }
}
