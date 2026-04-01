"""
Load synthetic student data into BigQuery and GCS.

Reads Parquet files from the data/synthetic/ directory and loads them
into BigQuery tables and GCS buckets.

Requires:
    - Parquet files exist in data/synthetic/ (run student_generator.py first)
    - GCP credentials configured (gcloud auth application-default login)
    - BigQuery dataset and GCS bucket exist (run Terraform first)

Ensures:
    - All 4 tables loaded into BigQuery
    - Parquet + CSV copies uploaded to GCS
    - Prints row counts and verification queries

Raises:
    - FileNotFoundError if Parquet files don't exist
    - google.api_core.exceptions.NotFound if dataset/bucket missing
"""

import os
import sys

import pandas as pd

# ---- Configuration ----

DEFAULT_DATA_DIR   = "data/synthetic"
DEFAULT_PROJECT_ID = os.environ.get( "GCP_PROJECT_ID", "ampe-to-meridian" )
DEFAULT_DATASET_ID = os.environ.get( "BQ_DATASET_ID", "meridian_student_data_dev" )
DEFAULT_GCS_BUCKET = os.environ.get( "GCS_TRAINING_BUCKET", "meridian-training-data-dev-ampe-to-meridian" )

TABLE_MAP = {
    "demographics"      : "student_demographics",
    "academic_records"   : "academic_records",
    "financial_aid"      : "financial_aid",
    "enrollment_events"  : "enrollment_events",
}


def load_to_bigquery(
    data_dir   : str = DEFAULT_DATA_DIR,
    project_id : str = DEFAULT_PROJECT_ID,
    dataset_id : str = DEFAULT_DATASET_ID,
):
    """
    Load all Parquet files into BigQuery tables.

    Requires:
        - data_dir contains demographics.parquet, academic_records.parquet, etc.
        - project_id and dataset_id point to existing BigQuery resources

    Ensures:
        - Tables are overwritten (WRITE_TRUNCATE) with fresh data
        - Returns dict of {table_name: row_count}
    """
    from google.cloud import bigquery

    client  = bigquery.Client( project=project_id )
    results = {}

    for parquet_name, bq_table in TABLE_MAP.items():
        path = os.path.join( data_dir, f"{parquet_name}.parquet" )
        if not os.path.exists( path ):
            raise FileNotFoundError( f"Missing: {path}. Run student_generator.py first." )

        df       = pd.read_parquet( path )
        table_id = f"{project_id}.{dataset_id}.{bq_table}"

        job_config = bigquery.LoadJobConfig(
            write_disposition = bigquery.WriteDisposition.WRITE_TRUNCATE,
            source_format     = bigquery.SourceFormat.PARQUET,
        )

        print( f"  Loading {parquet_name} -> {table_id} ({len( df ):,} rows)..." )
        job = client.load_table_from_dataframe( df, table_id, job_config=job_config )
        job.result()  # Wait for completion

        table        = client.get_table( table_id )
        results[ bq_table ] = table.num_rows
        print( f"    Done. Verified: {table.num_rows:,} rows in BigQuery." )

    return results


def upload_to_gcs(
    data_dir   : str = DEFAULT_DATA_DIR,
    bucket_name: str = DEFAULT_GCS_BUCKET,
):
    """
    Upload Parquet and CSV files to GCS training data bucket.

    Requires:
        - data_dir contains .parquet and .csv files
        - bucket_name points to existing GCS bucket with CMEK

    Ensures:
        - Files uploaded to gs://bucket_name/synthetic/
        - Returns list of GCS URIs
    """
    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket( bucket_name )
    uris   = []

    for filename in os.listdir( data_dir ):
        if filename.endswith( ( ".parquet", ".csv" ) ):
            local_path = os.path.join( data_dir, filename )
            blob_path  = f"synthetic/{filename}"
            blob       = bucket.blob( blob_path )

            print( f"  Uploading {filename} -> gs://{bucket_name}/{blob_path}..." )
            blob.upload_from_filename( local_path )
            uris.append( f"gs://{bucket_name}/{blob_path}" )

    return uris


# ---- CLI Entry Point ----

if __name__ == "__main__":

    print( "--- Loading Synthetic Data into BigQuery ---\n" )

    try:
        results = load_to_bigquery()
        print( "\n--- BigQuery Load Summary ---" )
        for table, count in results.items():
            print( f"  {table:30s}: {count:>8,} rows" )
    except ImportError:
        print( "google-cloud-bigquery not installed. Skipping BQ load." )
        print( "Install with: pip install google-cloud-bigquery" )
    except Exception as e:
        print( f"BigQuery load failed: {e}" )
        print( "Ensure GCP credentials and Terraform resources are configured." )

    print( "\n--- Uploading to GCS ---\n" )

    try:
        uris = upload_to_gcs()
        print( f"\n  Uploaded {len( uris )} files to GCS." )
    except ImportError:
        print( "google-cloud-storage not installed. Skipping GCS upload." )
    except Exception as e:
        print( f"GCS upload failed: {e}" )
        print( "Ensure GCP credentials and Terraform resources are configured." )
