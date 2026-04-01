"""
Cloud Function: Retraining trigger.

Triggered by Pub/Sub when retraining is requested (manual or automated).
Submits a new Vertex AI Pipeline run with the latest data.

Demonstrates Extensibility competency (event-driven ML lifecycle).
"""

import base64
import datetime
import json
import os


def trigger_retrain( event, context ):
    """
    Cloud Function entry point for retraining Pub/Sub trigger.

    Requires:
        - event contains Pub/Sub message with retraining config

    Ensures:
        - New pipeline job submitted to Vertex AI
        - Retraining metadata logged
    """
    import google.cloud.logging

    client = google.cloud.logging.Client()
    client.setup_logging()

    import logging
    logger = logging.getLogger( "retrain_trigger" )

    # Decode message
    config = {}
    if "data" in event:
        message = base64.b64decode( event[ "data" ] ).decode( "utf-8" )
        config  = json.loads( message )

    reason = config.get( "reason", "manual" )
    logger.info( f"Retraining triggered. Reason: {reason}" )

    project_id     = os.environ.get( "GCP_PROJECT_ID", "ampe-to-meridian" )
    region         = os.environ.get( "GCP_REGION", "us-central1" )
    pipeline_name  = config.get( "pipeline_name", "meridian-retention-pipeline" )

    try:
        resource_name = _trigger_retraining( project_id, region, pipeline_name, logger )
        logger.info(
            f"Pipeline submitted successfully: {resource_name}. "
            f"Config: {json.dumps( config, default=str )[ :200 ]}"
        )
    except Exception as e:
        logger.error( f"Failed to submit retraining job: {e}" )


def _trigger_retraining( project_id, region, pipeline_name="meridian-retention-pipeline", logger=None ):
    """
    Submit a Vertex AI Pipeline job for retraining.

    Requires:
        - project_id is a valid GCP project ID
        - region is a valid GCP region
        - pipeline_name is the name of the compiled pipeline template

    Ensures:
        - A new PipelineJob is submitted to Vertex AI
        - Returns the resource name of the submitted job

    Raises:
        - Exception if pipeline submission fails
    """
    import logging
    if logger is None:
        logger = logging.getLogger( "retrain_trigger" )

    from google.cloud import aiplatform

    aiplatform.init( project=project_id, location=region )

    # Compiled pipeline template location in GCS
    template_path = f"gs://meridian-pipeline-artifacts-dev-{project_id}/pipelines/{pipeline_name}.json"

    job = aiplatform.PipelineJob(
        display_name     = f"{pipeline_name}-retrain-{datetime.datetime.now().strftime( '%Y%m%d-%H%M%S' )}",
        template_path    = template_path,
        pipeline_root    = f"gs://meridian-pipeline-artifacts-dev-{project_id}/pipeline-runs",
        parameter_values = {
            "trigger" : "drift_alert",
        },
    )

    job.submit(
        service_account = f"meridian-pipeline-dev@{project_id}.iam.gserviceaccount.com",
    )

    logger.info( f"Retraining pipeline submitted: {job.resource_name}" )
    return job.resource_name
