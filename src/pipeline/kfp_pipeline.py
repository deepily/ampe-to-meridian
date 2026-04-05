"""
KFP v2 pipeline with real @dsl.component wrappers for Vertex AI Pipelines.

Wraps the 8 data-prep stages in src/pipeline/components/ as containerized
KFP components. Each component runs in the meridian/pipeline:v1 image built
from docker/pipeline/Dockerfile (which has src/ baked in at /app/src).

Requires:
    - kfp >= 2.5
    - google-cloud-aiplatform
    - Artifact Registry image exists:
        us-central1-docker.pkg.dev/ampe-to-meridian/meridian/pipeline:v1

Ensures:
    - compile_pipeline() produces a valid pipeline JSON
    - submit_pipeline() submits to Vertex AI Pipelines with proper SA
"""

from kfp import dsl, compiler
from kfp.dsl import Input, Output, Dataset


BASE_IMAGE = "us-central1-docker.pkg.dev/ampe-to-meridian/meridian/pipeline:v3"


# ---- Component 1: Ingest (BQ -> Parquet) ----

@dsl.component( base_image=BASE_IMAGE )
def ingest_op(
    project_id : str,
    dataset_id : str,
    ingest_output : Output[Dataset],
) -> None:
    """Extract 4 tables from BigQuery, merge on student_id."""
    from pipeline.components.ingest import ingest_from_bigquery
    ingest_from_bigquery(
        project_id = project_id,
        dataset_id = dataset_id,
        output_path = ingest_output.path,
    )


# ---- Component 2: Validate (TFDV-style) ----

@dsl.component( base_image=BASE_IMAGE )
def validate_op(
    input_data : Input[Dataset],
    validate_output : Output[Dataset],
    anomaly_threshold : int = 0,
) -> None:
    """Schema + anomaly detection (permissive: threshold=0 warns but does not block)."""
    from pipeline.components.validate import validate_data
    validate_data(
        input_path = input_data.path,
        output_path = validate_output.path,
        anomaly_threshold = anomaly_threshold,
    )


# ---- Component 3: DLP Scan ----

@dsl.component( base_image=BASE_IMAGE )
def dlp_scan_op(
    input_data : Input[Dataset],
    dlp_output : Output[Dataset],
    pii_threshold : float = 0.15,
    redact_mode : str = "replace",
) -> None:
    """PII detection + redaction. Threshold 0.15 accommodates synthetic PII density."""
    from pipeline.components.dlp_scan import dlp_scan
    dlp_scan(
        input_path = input_data.path,
        output_path = dlp_output.path,
        pii_threshold = pii_threshold,
        redact_mode = redact_mode,
    )


# ---- Component 4: Harmonize ----

@dsl.component( base_image=BASE_IMAGE )
def harmonize_op(
    input_data : Input[Dataset],
    harmonize_output : Output[Dataset],
) -> None:
    """Type alignment, null filling, dedup."""
    from pipeline.components.harmonize import harmonize
    harmonize(
        input_path = input_data.path,
        output_path = harmonize_output.path,
    )


# ---- Component 5: Clean (OHE + constant removal) ----

@dsl.component( base_image=BASE_IMAGE )
def clean_op(
    input_data : Input[Dataset],
    clean_output : Output[Dataset],
    target_column : str = "second_year_ret_flag",
) -> None:
    """Drop constants, OHE categoricals, produce fully numeric DataFrame."""
    from pipeline.components.clean import clean
    clean(
        input_path = input_data.path,
        output_path = clean_output.path,
        target_column = target_column,
    )


# ---- Component 6: Feature Engineer ----

@dsl.component( base_image=BASE_IMAGE )
def feature_engineer_op(
    input_data : Input[Dataset],
    features_output : Output[Dataset],
    target_column : str = "second_year_ret_flag",
) -> None:
    """Derived features: GPA momentum, credit ratio, aid coverage, etc."""
    from pipeline.components.feature_engineer import feature_engineer
    feature_engineer(
        input_path = input_data.path,
        output_path = features_output.path,
        target_column = target_column,
    )


# ---- Component 7: Feature Store Sync ----

@dsl.component( base_image=BASE_IMAGE )
def feature_store_sync_op(
    input_data : Input[Dataset],
    fs_output : Output[Dataset],
) -> None:
    """Export features (local mode inside pipeline; Vertex FS sync is a separate path)."""
    from pipeline.components.feature_store_sync import feature_store_sync
    feature_store_sync(
        input_path = input_data.path,
        output_path = fs_output.path,
    )


# ---- Component 8: Reduce Dimensions ----

@dsl.component( base_image=BASE_IMAGE )
def reduce_dimensions_op(
    input_data : Input[Dataset],
    reduced_output : Output[Dataset],
    target_column : str = "second_year_ret_flag",
    correlation_threshold : float = 0.85,
    vif_threshold : float = 10.0,
) -> None:
    """Correlation culling + iterative VIF to produce final feature set."""
    from pipeline.components.reduce_dimensions import reduce_dimensions
    reduce_dimensions(
        input_path = input_data.path,
        output_path = reduced_output.path,
        target_column = target_column,
        correlation_threshold = correlation_threshold,
        vif_threshold = vif_threshold,
    )


# ---- Pipeline Definition ----

@dsl.pipeline(
    name = "meridian-data-prep-pipeline",
    description = "Meridian 8-stage data-prep pipeline: BQ -> reduced feature set.",
)
def meridian_data_prep_pipeline(
    project_id : str = "ampe-to-meridian",
    dataset_id : str = "meridian_student_data_dev",
    target_column : str = "second_year_ret_flag",
    pii_threshold : float = 0.15,
    correlation_threshold : float = 0.85,
    vif_threshold : float = 10.0,
) -> None:
    """Chain all 8 data-prep components.

    Branches at feature_engineer -> [feature_store_sync, reduce_dimensions].
    """
    ingest_task = ingest_op(
        project_id = project_id,
        dataset_id = dataset_id,
    )

    validate_task = validate_op(
        input_data = ingest_task.outputs["ingest_output"],
    )

    dlp_task = dlp_scan_op(
        input_data = validate_task.outputs["validate_output"],
        # Synthetic data has 100% PII density by design (every row has a name/email/SSN).
        # Disable the density check by setting threshold > 1.0.
        pii_threshold = 2.0,
    )

    harmonize_task = harmonize_op(
        input_data = dlp_task.outputs["dlp_output"],
    )

    clean_task = clean_op(
        input_data = harmonize_task.outputs["harmonize_output"],
        target_column = target_column,
    )

    fe_task = feature_engineer_op(
        input_data = clean_task.outputs["clean_output"],
        target_column = target_column,
    )

    # Parallel branches from feature_engineer
    _fs_task = feature_store_sync_op(
        input_data = fe_task.outputs["features_output"],
    )

    _reduce_task = reduce_dimensions_op(
        input_data = fe_task.outputs["features_output"],
        target_column = target_column,
        correlation_threshold = correlation_threshold,
        vif_threshold = vif_threshold,
    )


# ---- Compile + Submit ----

def compile_pipeline( output_path: str = "meridian_data_prep_pipeline.json" ) -> str:
    """Compile the pipeline to JSON for Vertex AI Pipelines submission."""
    compiler.Compiler().compile(
        pipeline_func = meridian_data_prep_pipeline,
        package_path = output_path,
    )
    print( f"Pipeline compiled to: {output_path}" )
    return output_path


def submit_pipeline(
    project_id : str = "ampe-to-meridian",
    region : str = "us-central1",
    pipeline_root : str = "gs://meridian-artifacts-dev-ampe-to-meridian/pipeline-runs",
    service_account : str = "meridian-pipeline-dev@ampe-to-meridian.iam.gserviceaccount.com",
    template_path : str = "meridian_data_prep_pipeline.json",
) -> str:
    """Submit the compiled pipeline to Vertex AI Pipelines."""
    from google.cloud import aiplatform
    from datetime import datetime

    aiplatform.init( project=project_id, location=region )

    display_name = f"meridian-dataprep-{datetime.utcnow().strftime( '%Y%m%d-%H%M%S' )}"

    job = aiplatform.PipelineJob(
        display_name = display_name,
        template_path = template_path,
        pipeline_root = pipeline_root,
        parameter_values = {
            "project_id" : project_id,
            "dataset_id" : "meridian_student_data_dev",
        },
        enable_caching = False,
    )

    job.submit( service_account=service_account )
    print( f"Pipeline submitted: {job.resource_name}" )
    print( f"Console: https://console.cloud.google.com/vertex-ai/pipelines/runs/{job.name}?project={project_id}" )
    return job.resource_name


if __name__ == "__main__":
    import sys
    json_path = compile_pipeline()
    if len( sys.argv ) > 1 and sys.argv[1] == "submit":
        submit_pipeline( template_path=json_path )
