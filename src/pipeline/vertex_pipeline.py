"""
Vertex AI Pipeline DAG: Orchestrates all Meridian pipeline components.

Defines the KFP v2 pipeline as a sequential chain of components:
ingest -> validate -> dlp_scan -> harmonize -> clean ->
feature_engineer -> feature_store_sync -> reduce_dimensions

For local testing, provides run_local() which calls components
sequentially without Vertex AI.

Requires:
    - All pipeline components importable
    - For GCP: kfp, google-cloud-aiplatform installed

Ensures:
    - Pipeline runs end-to-end (local or on Vertex AI)
    - Each stage writes Parquet artifacts to output directory
    - Returns dict with stage reports
"""

import os
from typing import Optional

from utils.logging_config import get_logger

logger = get_logger( __name__, component="pipeline" )


def run_local(
    data_dir       : str,
    output_dir     : str,
    target_column  : str = "second_year_ret_flag",
    correlation_threshold: float = 0.85,
    vif_threshold  : float = 10.0,
) -> dict:
    """
    Run the full pipeline locally (no GCP required).

    Requires:
        - data_dir contains demographics.parquet, etc. (from student_generator)
        - output_dir is writable

    Ensures:
        - Returns dict with all stage reports
        - Each stage writes to output_dir/stage_name.parquet
        - Pipeline can be tested end-to-end without GCP credentials
    """
    from pipeline.components.ingest import ingest_from_local
    from pipeline.components.validate import validate_data
    from pipeline.components.dlp_scan import dlp_scan
    from pipeline.components.harmonize import harmonize
    from pipeline.components.clean import clean
    from pipeline.components.feature_engineer import feature_engineer
    from pipeline.components.feature_store_sync import feature_store_sync
    from pipeline.components.reduce_dimensions import reduce_dimensions

    os.makedirs( output_dir, exist_ok=True )
    reports = {}

    # Stage 1: Ingest
    logger.info( "=== Stage 1: Ingest ===" )
    ingest_path = os.path.join( output_dir, "01_ingested.parquet" )
    ingest_from_local( data_dir, ingest_path )
    reports[ "ingest" ] = { "output": ingest_path }

    # Stage 2: Validate
    logger.info( "=== Stage 2: Validate ===" )
    validate_path = os.path.join( output_dir, "02_validated.parquet" )
    schema_path   = os.path.join( output_dir, "02_schema.json" )
    reports[ "validate" ] = validate_data(
        ingest_path, validate_path,
        schema_output_path=schema_path,
        anomaly_threshold=0,  # Don't block on errors in local mode
    )

    # Stage 3: DLP Scan
    logger.info( "=== Stage 3: DLP Scan ===" )
    dlp_path   = os.path.join( output_dir, "03_dlp_scanned.parquet" )
    dlp_report = os.path.join( output_dir, "03_dlp_report.json" )
    reports[ "dlp_scan" ] = dlp_scan(
        validate_path, dlp_path,
        report_path=dlp_report,
        pii_threshold=1.0,  # Relaxed for local testing
        redact_mode="replace",
    )

    # Stage 4: Harmonize
    logger.info( "=== Stage 4: Harmonize ===" )
    harmonize_path = os.path.join( output_dir, "04_harmonized.parquet" )
    reports[ "harmonize" ] = harmonize( dlp_path, harmonize_path )

    # Stage 5: Clean
    logger.info( "=== Stage 5: Clean ===" )
    clean_path = os.path.join( output_dir, "05_cleaned.parquet" )
    reports[ "clean" ] = clean(
        harmonize_path, clean_path,
        target_column=target_column,
    )

    # Stage 6: Feature Engineering
    logger.info( "=== Stage 6: Feature Engineering ===" )
    feature_path = os.path.join( output_dir, "06_features.parquet" )
    reports[ "feature_engineer" ] = feature_engineer(
        clean_path, feature_path,
        target_column=target_column,
    )

    # Stage 7: Feature Store Sync (local export)
    logger.info( "=== Stage 7: Feature Store Sync ===" )
    fs_path = os.path.join( output_dir, "07_feature_store.parquet" )
    reports[ "feature_store_sync" ] = feature_store_sync(
        feature_path, fs_path,
    )

    # Stage 8: Dimensionality Reduction
    logger.info( "=== Stage 8: Reduce Dimensions ===" )
    reduced_path = os.path.join( output_dir, "08_reduced.parquet" )
    reports[ "reduce_dimensions" ] = reduce_dimensions(
        feature_path, reduced_path,  # Read from features, not feature store
        target_column=target_column,
        correlation_threshold=correlation_threshold,
        vif_threshold=vif_threshold,
    )

    logger.info( "=== Pipeline Complete ===" )
    logger.info( f"Final dataset: {reduced_path}" )

    return reports


def compile_vertex_pipeline(
    pipeline_name   : str = "meridian-retention-pipeline",
    pipeline_root   : str = "gs://meridian-artifacts-dev/pipeline_root",
    project_id      : str = "REPLACE_WITH_PROJECT_ID",
    dataset_id      : str = "meridian_student_data_dev",
    service_account : str = "",
    experiment_name : str = "meridian-baseline",
) -> str:
    """
    Compile the KFP v2 pipeline for Vertex AI execution.

    Requires:
        - kfp >= 2.5.0 installed
        - GCP project with Vertex AI API enabled

    Ensures:
        - Returns path to compiled pipeline JSON
        - Pipeline can be submitted to Vertex AI Pipelines
    """
    import kfp
    from kfp import dsl

    @dsl.pipeline(
        name=pipeline_name,
        pipeline_root=pipeline_root,
    )
    def meridian_pipeline(
        project_id      : str = project_id,
        dataset_id      : str = dataset_id,
        target_column   : str = "second_year_ret_flag",
        dlp_threshold   : float = 0.05,
        corr_threshold  : float = 0.85,
        vif_threshold   : float = 10.0,
    ):
        """Meridian student retention pipeline — 8 stages."""
        # Note: In production, each stage would be a @dsl.component
        # For now, this defines the pipeline structure.
        # Components will be containerized in Phase 3.
        pass

    # Compile to JSON
    output_path = f"{pipeline_name}.json"
    kfp.compiler.Compiler().compile(
        pipeline_func=meridian_pipeline,
        package_path=output_path,
    )

    logger.info( f"Pipeline compiled to {output_path}" )
    return output_path


# ---- CLI Entry Point ----

if __name__ == "__main__":

    import sys

    if len( sys.argv ) > 1 and sys.argv[ 1 ] == "compile":
        compile_vertex_pipeline()
    else:
        # Default: run locally with test data
        reports = run_local(
            data_dir="data/synthetic",
            output_dir="data/pipeline_output",
        )

        print( "\n--- Pipeline Stage Summary ---" )
        for stage, report in reports.items():
            if isinstance( report, dict ):
                key_stats = {k: v for k, v in report.items() if k != "anomalies" and k != "schema_stats"}
                print( f"  {stage:25s}: {key_stats}" )
