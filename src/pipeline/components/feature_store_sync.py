"""
Feature Store sync component: Write features to Vertex AI Feature Store.

This component has NO equivalent in AMPE (features stored in S3/memory).
Demonstrates AI Lifecycle Management competency.

Requires:
    - Engineered Parquet with student features
    - Vertex AI Feature Store configured (or mock for testing)

Ensures:
    - Features written to Feature Store with student_id as entity
    - Returns sync report with feature count and entity count
"""

import json
from typing import Optional

import pandas as pd

from utils.io_utils import ensure_parent_dir, write_parquet
from utils.logging_config import get_logger

logger = get_logger( __name__ )

# Features to sync (subset of engineered features)
FEATURE_COLUMNS = [
    "hs_gpa", "sat_score", "act_score",
    "cumulative_gpa", "term_gpa", "credits_earned", "credits_attempted",
    "efc", "total_aid_amount", "loan_amount", "unmet_need",
    "campus_distance_miles", "cohort_year",
    "gpa_change", "gpa_momentum", "credit_ratio", "credit_deficit",
    "aid_coverage_ratio", "loan_dependency", "distance_bin", "test_score_composite",
]


def feature_store_sync(
    input_path     : str,
    output_path    : str,
    report_path    : Optional[str] = None,
    use_vertex_fs  : bool = False,
    project_id     : Optional[str] = None,
    region         : Optional[str] = None,
    featurestore_id: Optional[str] = None,
) -> dict:
    """
    Sync features to Vertex AI Feature Store (or local export for testing).

    Requires:
        - input_path points to engineered Parquet with student_id column
        - FEATURE_COLUMNS subset exists in DataFrame

    Ensures:
        - Returns dict with sync stats (entities synced, features synced)
        - Writes feature export to output_path
        - If use_vertex_fs=True, syncs to Vertex AI Feature Store
    """
    logger.info( f"Syncing features from {input_path}" )
    df = pd.read_parquet( input_path )

    # Select available feature columns
    available = [c for c in FEATURE_COLUMNS if c in df.columns]
    missing   = [c for c in FEATURE_COLUMNS if c not in df.columns]

    if missing:
        logger.warning( f"Missing feature columns: {missing}" )

    # Build feature export (student_id + features)
    id_col = "student_id" if "student_id" in df.columns else df.columns[ 0 ]
    export_cols = [id_col] + available
    feature_df  = df[ export_cols ].copy()

    # Deduplicate by entity ID
    feature_df = feature_df.drop_duplicates( subset=[id_col] )

    if use_vertex_fs and project_id:
        _sync_to_vertex( feature_df, id_col, project_id, region, featurestore_id )
    else:
        logger.info( "Local mode: exporting features as Parquet (no Vertex AI Feature Store)" )

    # Save feature export
    write_parquet( feature_df, output_path )

    report = {
        "entities_synced"  : len( feature_df ),
        "features_synced"  : len( available ),
        "features_missing" : missing,
        "mode"             : "vertex_ai" if use_vertex_fs else "local",
    }

    if report_path:
        ensure_parent_dir( report_path )
        with open( report_path, "w" ) as f:
            json.dump( report, f, indent=2 )

    logger.info(
        f"Feature Store sync complete: {report[ 'entities_synced' ]:,} entities, "
        f"{report[ 'features_synced' ]} features -> {output_path}"
    )

    # Pass through original data (not just features) for downstream components
    df.to_parquet( output_path.replace( "features", "passthrough" ) if "features" in output_path else output_path, index=False )

    return report


def _sync_to_vertex(
    feature_df     : pd.DataFrame,
    id_col         : str,
    project_id     : str,
    region         : str,
    featurestore_id: str,
):
    """
    Sync features to Vertex AI Feature Store via batch import.

    Requires:
        - google-cloud-aiplatform installed
        - Feature Store and entity type pre-created via Terraform
    """
    from google.cloud import aiplatform

    aiplatform.init( project=project_id, location=region )

    entity_type = aiplatform.featurestore.EntityType(
        entity_type_name=f"projects/{project_id}/locations/{region}/featurestores/{featurestore_id}/entityTypes/student"
    )

    logger.info( f"Importing {len( feature_df ):,} entities into Feature Store..." )

    entity_type.ingest_from_df(
        feature_ids=[c for c in feature_df.columns if c != id_col],
        feature_time=pd.Timestamp.now(),
        df_source=feature_df,
        entity_id_field=id_col,
    )

    logger.info( "Feature Store import complete." )
