"""
Deploy component: Deploy model to Vertex AI Prediction endpoint.

Supports traffic splitting for A/B testing between model versions.
Falls back to local serving simulation for testing.

Demonstrates Availability Design and API Design & Versioning competencies.

Requires:
    - Registered model (pickle file from register stage)
    - For GCP: Vertex AI API enabled, service account with aiplatform.user role

Ensures:
    - Model deployed to endpoint with configurable traffic split
    - Returns endpoint URI and deployment metadata
"""

import json
import os
import pickle
from typing import Optional

import numpy as np
import pandas as pd

from utils.logging_config import get_logger

logger = get_logger( __name__, component="deploy" )


def deploy(
    model_path            : str,
    input_path            : str,
    output_dir            : str,
    target_column         : str = "second_year_ret_flag",
    traffic_split         : dict = None,
    use_vertex_endpoint   : bool = False,
    project_id            : Optional[str] = None,
    region                : Optional[str] = None,
    serving_container_uri : Optional[str] = None,
    undeploy_previous     : bool = False,
) -> dict:
    """
    Deploy model and generate batch predictions.

    Requires:
        - model_path points to valid pickle
        - input_path points to reduced Parquet

    Ensures:
        - Batch predictions written to output_dir
        - Returns deployment report with predictions summary
    """
    if traffic_split is None:
        traffic_split = {"primary": 100}

    logger.info( f"Deploying model from {model_path}" )

    os.makedirs( output_dir, exist_ok=True )

    # Load model
    with open( model_path, "rb" ) as f:
        model = pickle.load( f )

    # Load data
    df = pd.read_parquet( input_path )

    drop_cols = [target_column]
    if "student_id" in df.columns:
        drop_cols.append( "student_id" )

    X = df.drop( columns=drop_cols, errors="ignore" )
    y = df[ target_column ].astype( int ) if target_column in df.columns else None

    # Generate batch predictions
    predictions   = model.predict( X )
    probabilities = model.predict_proba( X )[ :, 1 ] if hasattr( model, "predict_proba" ) else predictions.astype( float )

    # Build prediction DataFrame
    pred_df = pd.DataFrame( {
        "student_id"           : df[ "student_id" ].values if "student_id" in df.columns else range( len( df ) ),
        "predicted_class"      : predictions.astype( int ),
        "predicted_probability": np.round( probabilities, 4 ),
        "model_version"        : "v1_local",
    } )

    if y is not None:
        pred_df[ "actual_class" ] = y.values

    # Save predictions
    pred_path = os.path.join( output_dir, "predictions.parquet" )
    pred_df.to_parquet( pred_path, index=False )

    # Save as CSV for readability
    csv_path = os.path.join( output_dir, "predictions.csv" )
    pred_df.to_csv( csv_path, index=False )

    # Compute prediction stats
    pred_stats = {
        "total_predictions"    : len( pred_df ),
        "predicted_retained"   : int( ( predictions == 1 ).sum() ),
        "predicted_not_retained": int( ( predictions == 0 ).sum() ),
        "mean_probability"     : float( np.mean( probabilities ) ),
        "median_probability"   : float( np.median( probabilities ) ),
    }

    if y is not None:
        from sklearn.metrics import accuracy_score, roc_auc_score
        pred_stats[ "batch_accuracy" ] = float( accuracy_score( y, predictions ) )
        pred_stats[ "batch_auc" ]      = float( roc_auc_score( y, probabilities ) )

    if use_vertex_endpoint and project_id:
        endpoint_info = _deploy_to_vertex(
            model_path, project_id, region, traffic_split,
            serving_container_uri=serving_container_uri,
            undeploy_previous=undeploy_previous,
        )
    else:
        endpoint_info = {
            "mode"           : "local_batch",
            "traffic_split"  : traffic_split,
            "predictions_path": pred_path,
        }

    report = {
        **pred_stats,
        **endpoint_info,
    }

    report_path = os.path.join( output_dir, "deployment_report.json" )
    with open( report_path, "w" ) as f:
        json.dump( report, f, indent=2, default=str )

    logger.info(
        f"Deployment complete: {pred_stats[ 'total_predictions' ]:,} predictions, "
        f"accuracy={pred_stats.get( 'batch_accuracy', 'N/A' )}"
    )

    return report


def _deploy_to_vertex(
    model_path            : str,
    project_id            : str,
    region                : str,
    traffic_split         : dict,
    serving_container_uri : Optional[str] = None,
    undeploy_previous     : bool = False,
) -> dict:
    """
    Deploy model to Vertex AI Prediction endpoint with traffic splitting.

    Requires:
        - model_path points to a valid model artifact directory
        - project_id is a valid GCP project ID
        - region is a valid GCP region

    Ensures:
        - Model uploaded to Vertex AI Model Registry
        - Endpoint created or reused
        - New model deployed with traffic split
        - Previous model optionally undeployed
        - Returns deployment metadata with endpoint info

    Raises:
        - Logs error and re-raises if deployment fails
    """
    from google.cloud import aiplatform

    aiplatform.init( project=project_id, location=region )

    # Default to pre-built sklearn container if no custom container specified
    if serving_container_uri is None:
        serving_container_uri = "us-docker.pkg.dev/vertex-ai/prediction/sklearn-cpu.1-3:latest"

    # Upload model
    try:
        model = aiplatform.Model.upload(
            display_name               = "meridian-retention-classifier",
            artifact_uri               = os.path.dirname( model_path ),
            serving_container_image_uri = serving_container_uri,
        )
        logger.info( f"Model uploaded: {model.resource_name}" )
    except Exception as e:
        logger.error( f"Model upload failed: {e}" )
        raise

    # Create or get endpoint
    try:
        endpoints = aiplatform.Endpoint.list(
            filter='display_name="meridian-retention-endpoint"',
        )

        if endpoints:
            endpoint = endpoints[ 0 ]
            logger.info( f"Reusing existing endpoint: {endpoint.resource_name}" )
        else:
            endpoint = aiplatform.Endpoint.create(
                display_name = "meridian-retention-endpoint",
            )
            logger.info( f"Created new endpoint: {endpoint.resource_name}" )
    except Exception as e:
        logger.error( f"Endpoint creation/lookup failed: {e}" )
        raise

    # Capture existing deployed models for traffic splitting / undeploy
    existing_models = {}
    try:
        deployed = endpoint.gca_resource.deployed_models
        for dm in deployed:
            existing_models[ dm.id ] = dm.display_name
    except Exception:
        pass  # No existing deployments

    # Build traffic split: new model gets primary percentage, rest distributed
    primary_pct   = traffic_split.get( "primary", 100 )
    remaining_pct = 100 - primary_pct

    # Deploy new model version
    try:
        import datetime
        version_label = datetime.datetime.now().strftime( "%Y%m%d-%H%M%S" )

        model.deploy(
            endpoint                    = endpoint,
            deployed_model_display_name = f"meridian-{version_label}",
            machine_type                = "n1-standard-2",
            min_replica_count           = 1,
            max_replica_count           = 3,
            traffic_percentage          = primary_pct,
        )
        logger.info( f"Model deployed with {primary_pct}% traffic" )
    except Exception as e:
        logger.error( f"Model deployment failed: {e}" )
        raise

    # Undeploy previous model versions if requested
    undeployed_models = []
    if undeploy_previous and existing_models:
        for model_id, display_name in existing_models.items():
            try:
                endpoint.undeploy( deployed_model_id=model_id )
                undeployed_models.append( display_name )
                logger.info( f"Undeployed previous model: {display_name}" )
            except Exception as e:
                logger.warning( f"Failed to undeploy {display_name}: {e}" )

    return {
        "mode"              : "vertex_ai",
        "endpoint_name"     : endpoint.resource_name,
        "endpoint_uri"      : endpoint.gca_resource.name,
        "model_name"        : model.resource_name,
        "traffic_split"     : traffic_split,
        "serving_container" : serving_container_uri,
        "undeployed_models" : undeployed_models,
    }
