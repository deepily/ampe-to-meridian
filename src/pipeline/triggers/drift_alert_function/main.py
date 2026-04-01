"""
Cloud Function: Drift alert handler.

Triggered by Pub/Sub when model monitoring detects drift.
Sends notification and optionally triggers pipeline retraining.

Demonstrates Extensibility competency (event-driven architecture).

Requires:
    - Pub/Sub subscription on drift alert topic
    - Cloud Functions runtime

Ensures:
    - Logs drift alert details
    - Optionally triggers retraining pipeline via Vertex AI
"""

import base64
import json
import os


def handle_drift_alert( event, context ):
    """
    Cloud Function entry point for drift alert Pub/Sub messages.

    Requires:
        - event contains Pub/Sub message with drift report

    Ensures:
        - Drift alert logged
        - Retraining triggered if alert severity is HIGH
    """
    import google.cloud.logging

    client = google.cloud.logging.Client()
    client.setup_logging()

    import logging
    logger = logging.getLogger( "drift_alert" )

    # Decode Pub/Sub message
    if "data" in event:
        message = base64.b64decode( event[ "data" ] ).decode( "utf-8" )
        alert   = json.loads( message )
    else:
        logger.warning( "No data in Pub/Sub message" )
        return

    drifted_count = alert.get( "drifted_features", 0 )
    pred_drifted  = alert.get( "prediction_drift", {} ).get( "drifted", False )

    logger.warning(
        f"DRIFT ALERT: {drifted_count} features drifted, "
        f"prediction drift={'YES' if pred_drifted else 'NO'}"
    )

    # Trigger retraining if significant drift
    if drifted_count > 3 or pred_drifted:
        logger.info( "Drift exceeds threshold — triggering retraining pipeline" )
        _trigger_retraining( alert )
    else:
        logger.info( "Drift within acceptable range — monitoring only" )


def _trigger_retraining( alert: dict ):
    """
    Trigger Vertex AI Pipeline rerun for retraining.

    Requires:
        - alert is a dict containing drift detection details
        - GCP_PROJECT_ID and GCP_REGION environment variables set

    Ensures:
        - A new PipelineJob is submitted to Vertex AI
        - Drift alert metadata is passed as pipeline parameters

    Raises:
        - Logs error if pipeline submission fails
    """
    import datetime
    import logging

    logger = logging.getLogger( "drift_alert" )

    project_id     = os.environ.get( "GCP_PROJECT_ID", "ampe-to-meridian" )
    region         = os.environ.get( "GCP_REGION", "us-central1" )
    pipeline_name  = "meridian-retention-pipeline"

    try:
        from google.cloud import aiplatform

        aiplatform.init( project=project_id, location=region )

        # Compiled pipeline template location in GCS
        template_path = f"gs://meridian-pipeline-artifacts-dev-{project_id}/pipelines/{pipeline_name}.json"

        job = aiplatform.PipelineJob(
            display_name     = f"{pipeline_name}-drift-retrain-{datetime.datetime.now().strftime( '%Y%m%d-%H%M%S' )}",
            template_path    = template_path,
            pipeline_root    = f"gs://meridian-pipeline-artifacts-dev-{project_id}/pipeline-runs",
            parameter_values = {
                "trigger"          : "drift_alert",
                "drifted_features" : str( alert.get( "drifted_features", 0 ) ),
                "prediction_drift" : str( alert.get( "prediction_drift", {} ).get( "drifted", False ) ),
            },
        )

        job.submit(
            service_account = f"meridian-pipeline-dev@{project_id}.iam.gserviceaccount.com",
        )

        logger.info( f"Retraining pipeline submitted: {job.resource_name}" )

    except Exception as e:
        logger.error( f"Failed to trigger retraining: {e}" )
