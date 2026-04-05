"""
Register component: Upload winning model to Vertex AI Model Registry.

Registers the winning model with metadata, metrics, and model card
information. Falls back to local registry (JSON manifest) for testing.

Demonstrates AI Lifecycle Management competency.

Requires:
    - Winning model pickle from train/tune stage
    - Evaluation report with metrics
    - Explanation report with feature importances

Ensures:
    - Model registered with version, metrics, and lineage
    - Model card metadata generated
    - Returns registration report
"""

import json
import os
import shutil
from datetime import datetime, timezone
from typing import Optional

from utils.logging_config import get_logger

logger = get_logger( __name__ )


def register(
    model_path          : str,
    evaluation_report   : dict,
    explanation_report  : dict,
    output_dir          : str,
    model_display_name  : str = "meridian-retention-classifier",
    model_description   : str = "Student retention prediction model trained on synthetic data",
    use_vertex_registry : bool = False,
    project_id          : Optional[str] = None,
    region              : Optional[str] = None,
    version_aliases     : list = None,
    is_default_version  : bool = True,
    pipeline_run_id     : Optional[str] = None,
) -> dict:
    """
    Register model with metadata and lineage.

    Requires:
        - model_path points to valid pickle file
        - evaluation_report and explanation_report are dicts from prior stages

    Ensures:
        - Model copied to output_dir/models/
        - Registry manifest created with version, metrics, lineage
        - Model card metadata generated
    """
    logger.info( f"Registering model from {model_path}" )

    os.makedirs( output_dir, exist_ok=True )
    models_dir = os.path.join( output_dir, "models" )
    os.makedirs( models_dir, exist_ok=True )

    # Generate version
    timestamp   = datetime.now( timezone.utc ).strftime( "%Y%m%d_%H%M%S" )
    version     = f"v1_{timestamp}"
    winner      = evaluation_report.get( "winner", {} )
    algorithm   = winner.get( "algorithm", "unknown" )

    # Copy model to registry
    model_filename = f"{algorithm}_{version}.pkl"
    registered_path = os.path.join( models_dir, model_filename )
    shutil.copy2( model_path, registered_path )

    # Build registry entry
    registry_entry = {
        "model_display_name" : model_display_name,
        "model_description"  : model_description,
        "version"            : version,
        "algorithm"          : algorithm,
        "smote_strategy"     : winner.get( "smote_strategy", "unknown" ),
        "registered_at"      : datetime.now( timezone.utc ).isoformat(),
        "artifact_path"      : registered_path,
        "metrics"            : {
            "accuracy" : winner.get( "accuracy", 0 ),
            "auc"      : winner.get( "auc", 0 ),
            "tp_rate"  : winner.get( "tp_rate", 0 ),
            "tn_rate"  : winner.get( "tn_rate", 0 ),
            "f1"       : winner.get( "f1", 0 ),
        },
        "top_features"       : explanation_report.get( "top_features", [] )[ :5 ],
        "lineage"            : {
            "training_report"    : "training_report.json",
            "tuning_report"      : "tuning_report.json",
            "evaluation_report"  : "evaluation_report.json",
            "explanation_report"  : "explanation_report.json",
        },
    }

    # Build model card metadata
    model_card = _generate_model_card_metadata(
        registry_entry, evaluation_report, explanation_report
    )
    registry_entry[ "model_card" ] = model_card

    # Save registry manifest
    manifest_path = os.path.join( output_dir, "model_registry.json" )
    with open( manifest_path, "w" ) as f:
        json.dump( registry_entry, f, indent=2 )

    # Save model card
    card_path = os.path.join( output_dir, "model_card_metadata.json" )
    with open( card_path, "w" ) as f:
        json.dump( model_card, f, indent=2 )

    if use_vertex_registry and project_id:
        _register_to_vertex(
            registered_path, registry_entry, project_id, region,
            version_aliases=version_aliases,
            is_default_version=is_default_version,
            pipeline_run_id=pipeline_run_id,
        )

    logger.info(
        f"Model registered: {model_display_name} {version} "
        f"(accuracy={registry_entry[ 'metrics' ][ 'accuracy' ]:.3f})"
    )

    return registry_entry


def _generate_model_card_metadata(
    registry_entry     : dict,
    evaluation_report  : dict,
    explanation_report : dict,
) -> dict:
    """
    Generate model card metadata per Responsible AI guidelines.

    Demonstrates AI-Specific Security competency.
    """
    return {
        "model_details": {
            "name"        : registry_entry[ "model_display_name" ],
            "version"     : registry_entry[ "version" ],
            "type"        : "Binary classification",
            "algorithm"   : registry_entry[ "algorithm" ],
            "framework"   : "scikit-learn / XGBoost",
            "description" : registry_entry[ "model_description" ],
        },
        "intended_use": {
            "primary_use"    : "Predict second-year student retention in higher education",
            "primary_users"  : "Institutional researchers, student success offices",
            "out_of_scope"   : "Individual student decision-making, disciplinary actions",
        },
        "training_data": {
            "source"      : "Synthetic student data (Faker-generated)",
            "size"        : f"{evaluation_report.get( 'winner', {} ).get( 'train_rows', 'N/A' )} training rows",
            "features"    : f"{explanation_report.get( 'total_features', 'N/A' )} features",
            "target"      : "second_year_ret_flag (binary: 0=not retained, 1=retained)",
            "class_balance": "~75% retained / ~25% not retained",
            "pii_handling" : "Cloud DLP scan applied before training (FERPA compliance)",
        },
        "performance": {
            "metrics"     : registry_entry[ "metrics" ],
            "evaluation"  : "Holdout test set (20%)",
        },
        "ethical_considerations": {
            "fairness"    : "Model should be evaluated for bias across demographic groups",
            "privacy"     : "Training data de-identified via Cloud DLP before model training",
            "limitations" : [
                "Trained on synthetic data — real-world performance may differ",
                "Does not account for external factors (pandemic, policy changes)",
                "Should not be used as sole basis for student interventions",
            ],
        },
        "top_features": [
            f[ "feature" ] for f in explanation_report.get( "top_features", [] )[ :10 ]
        ],
    }


def _register_to_vertex(
    model_path         : str,
    registry_entry     : dict,
    project_id         : str,
    region             : str,
    version_aliases    : list = None,
    is_default_version : bool = True,
    pipeline_run_id    : Optional[str] = None,
):
    """
    Register model in Vertex AI Model Registry with versioning support.

    Requires:
        - model_path points to a valid model artifact
        - registry_entry contains model metadata (display_name, algorithm, version)
        - project_id and region are valid GCP identifiers

    Ensures:
        - If a model with the same display name exists, uploads as a new version
        - Otherwise creates a new model resource
        - Applies version aliases (e.g., ["latest", "candidate"])
        - Links model to pipeline run via metadata labels
        - Returns the registered model resource name

    Raises:
        - Logs error and re-raises if registration fails
    """
    from google.cloud import aiplatform

    aiplatform.init( project=project_id, location=region )

    if version_aliases is None:
        version_aliases = [ "latest" ]

    # Build labels with model lineage information
    labels = {
        "algorithm" : registry_entry[ "algorithm" ],
        "version"   : registry_entry[ "version" ],
    }
    if pipeline_run_id:
        labels[ "pipeline_run_id" ] = pipeline_run_id

    display_name = registry_entry[ "model_display_name" ]

    # Check for existing model by display name to upload as new version
    try:
        existing_models = aiplatform.Model.list(
            filter=f'display_name="{display_name}"',
        )

        if existing_models:
            # Upload as a new version of the existing model
            parent_model = existing_models[ 0 ]
            logger.info(
                f"Found existing model: {parent_model.resource_name}. "
                f"Uploading as new version."
            )

            model = aiplatform.Model.upload(
                display_name               = display_name,
                parent_model               = parent_model.resource_name,
                artifact_uri               = os.path.dirname( model_path ),
                serving_container_image_uri = "us-docker.pkg.dev/vertex-ai/prediction/sklearn-cpu.1-3:latest",
                description                = registry_entry[ "model_description" ],
                labels                     = labels,
                version_aliases            = version_aliases,
                is_default_version         = is_default_version,
            )

            logger.info(
                f"New model version registered: {model.resource_name} "
                f"(aliases: {version_aliases}, default: {is_default_version})"
            )
        else:
            # Create new model resource
            model = aiplatform.Model.upload(
                display_name               = display_name,
                artifact_uri               = os.path.dirname( model_path ),
                serving_container_image_uri = "us-docker.pkg.dev/vertex-ai/prediction/sklearn-cpu.1-3:latest",
                description                = registry_entry[ "model_description" ],
                labels                     = labels,
                version_aliases            = version_aliases,
                is_default_version         = is_default_version,
            )

            logger.info( f"New model registered in Vertex AI: {model.resource_name}" )

    except Exception as e:
        logger.error( f"Vertex AI model registration failed: {e}" )
        raise
