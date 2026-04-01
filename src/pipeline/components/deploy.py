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
    model_path          : str,
    input_path          : str,
    output_dir          : str,
    target_column       : str = "second_year_ret_flag",
    traffic_split       : dict = None,
    use_vertex_endpoint : bool = False,
    project_id          : Optional[str] = None,
    region              : Optional[str] = None,
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
        endpoint_info = _deploy_to_vertex( model_path, project_id, region, traffic_split )
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
    model_path    : str,
    project_id    : str,
    region        : str,
    traffic_split : dict,
) -> dict:
    """Deploy model to Vertex AI Prediction endpoint with traffic splitting."""
    from google.cloud import aiplatform

    aiplatform.init( project=project_id, location=region )

    # Upload model
    model = aiplatform.Model.upload(
        display_name="meridian-retention-classifier",
        artifact_uri=os.path.dirname( model_path ),
        serving_container_image_uri="us-docker.pkg.dev/vertex-ai/prediction/sklearn-cpu.1-3:latest",
    )

    # Create or get endpoint
    endpoints = aiplatform.Endpoint.list(
        filter='display_name="meridian-retention-endpoint"',
    )

    if endpoints:
        endpoint = endpoints[ 0 ]
    else:
        endpoint = aiplatform.Endpoint.create(
            display_name="meridian-retention-endpoint",
        )

    # Deploy with traffic split
    model.deploy(
        endpoint=endpoint,
        deployed_model_display_name="meridian-v1",
        machine_type="n1-standard-2",
        min_replica_count=1,
        max_replica_count=3,
        traffic_percentage=traffic_split.get( "primary", 100 ),
    )

    return {
        "mode"          : "vertex_ai",
        "endpoint_name" : endpoint.resource_name,
        "endpoint_uri"  : endpoint.gca_resource.name,
        "traffic_split" : traffic_split,
    }
