"""
Ingest component: Extract data from BigQuery to Parquet.

Replaces AMPE's SQL->Redshift extract + Docker cache with
BigQuery client reads written to GCS-staged Parquet files.

Requires:
    - BigQuery dataset with student tables populated
    - GCS bucket for staging output (or local path for testing)

Ensures:
    - Returns a merged DataFrame with demographics + academics + financial + enrollment
    - All tables joined on student_id
    - Output written as Parquet to output_path
"""

import os
from typing import Optional

import pandas as pd

from utils.logging_config import get_logger

logger = get_logger( __name__, component="ingest" )


def ingest_from_bigquery(
    project_id : str,
    dataset_id : str,
    output_path: str,
) -> str:
    """
    Extract all 4 student tables from BigQuery and merge into single Parquet.

    Requires:
        - project_id, dataset_id point to existing BQ resources
        - GCP credentials configured

    Ensures:
        - Returns path to merged Parquet file
        - Merged on student_id with left joins from demographics
    """
    from utils.bq_client import BigQueryClient

    bq = BigQueryClient( project_id )

    tables = {
        "demographics"     : f"{project_id}.{dataset_id}.student_demographics",
        "academic_records"  : f"{project_id}.{dataset_id}.academic_records",
        "financial_aid"     : f"{project_id}.{dataset_id}.financial_aid",
        "enrollment_events" : f"{project_id}.{dataset_id}.enrollment_events",
    }

    dfs = {}
    for name, table_id in tables.items():
        dfs[ name ] = bq.list_rows( table_id )

    merged = merge_tables( dfs )

    os.makedirs( os.path.dirname( output_path ) or ".", exist_ok=True )
    merged.to_parquet( output_path, index=False )
    logger.info( f"Merged dataset: {len( merged ):,} rows -> {output_path}" )

    return output_path


def ingest_from_local(
    data_dir   : str,
    output_path: str,
) -> str:
    """
    Extract from local Parquet files (for testing without GCP).

    Requires:
        - data_dir contains demographics.parquet, academic_records.parquet, etc.

    Ensures:
        - Returns path to merged Parquet file
    """
    dfs = {}
    for name in ["demographics", "academic_records", "financial_aid", "enrollment_events"]:
        path = os.path.join( data_dir, f"{name}.parquet" )
        if os.path.exists( path ):
            dfs[ name ] = pd.read_parquet( path )
            logger.info( f"Read {name}: {len( dfs[ name ] ):,} rows from {path}" )
        else:
            path_csv = os.path.join( data_dir, f"{name}.csv" )
            if os.path.exists( path_csv ):
                dfs[ name ] = pd.read_csv( path_csv )

    merged = merge_tables( dfs )

    os.makedirs( os.path.dirname( output_path ) or ".", exist_ok=True )
    merged.to_parquet( output_path, index=False )
    logger.info( f"Merged dataset: {len( merged ):,} rows -> {output_path}" )

    return output_path


def merge_tables( dfs: dict ) -> pd.DataFrame:
    """
    Merge 4 student tables into single analysis DataFrame.

    Requires:
        - dfs contains 'demographics', 'enrollment_events' at minimum
        - All DataFrames have 'student_id' column

    Ensures:
        - Returns DataFrame with enrollment-level granularity
        - One row per student enrollment event
        - Demographics and financial aid joined via left join
    """
    # Start from enrollment events (has the target variable)
    enrollment = dfs[ "enrollment_events" ]

    # Filter to enrollment events only (has retention flag)
    enrolled = enrollment[ enrollment[ "event_type" ] == "enrollment" ].copy()

    # Join demographics
    if "demographics" in dfs:
        demo = dfs[ "demographics" ]
        # Drop PII columns that will be handled by DLP (keep for DLP scan first)
        enrolled = enrolled.merge( demo, on="student_id", how="left", suffixes=( "", "_demo" ) )

    # Join financial aid
    if "financial_aid" in dfs:
        fin = dfs[ "financial_aid" ]
        enrolled = enrolled.merge( fin, on="student_id", how="left", suffixes=( "", "_fin" ) )

    # Join academic records (aggregate to latest term per student)
    if "academic_records" in dfs:
        academic = dfs[ "academic_records" ]
        # Get latest term record per student
        latest_academic = (
            academic
            .sort_values( "term_code", ascending=False )
            .groupby( "student_id" )
            .first()
            .reset_index()
        )
        enrolled = enrolled.merge( latest_academic, on="student_id", how="left", suffixes=( "", "_acad" ) )

    logger.info( f"Merged: {len( enrolled ):,} rows, {len( enrolled.columns )} columns" )
    return enrolled
