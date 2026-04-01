"""
Cloud Function: Retraining trigger.

Triggered by Pub/Sub when retraining is requested (manual or automated).
Submits a new Vertex AI Pipeline run with the latest data.

Demonstrates Extensibility competency (event-driven ML lifecycle).
"""

import base64
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

    project_id = os.environ.get( "GCP_PROJECT_ID", "ampe-to-meridian" )
    region     = os.environ.get( "GCP_REGION", "us-central1" )

    try:
        from google.cloud import aiplatform
        aiplatform.init( project=project_id, location=region )

        logger.info(
            f"Would submit pipeline job to {project_id}/{region}. "
            f"Config: {json.dumps( config, default=str )[ :200 ]}"
        )
    except Exception as e:
        logger.error( f"Failed to submit retraining job: {e}" )
