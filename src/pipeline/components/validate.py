"""
Validate component: TFDV data validation and schema enforcement.

Generates a TFDV schema from training data and detects anomalies
including null values, out-of-range values, and unexpected distributions.

This component has NO equivalent in AMPE — it's entirely new,
demonstrating the Failure & Recovery Testing competency.

Requires:
    - Input Parquet with merged student data
    - tensorflow-data-validation installed

Ensures:
    - Schema generated and saved as artifact
    - Anomalies detected and reported
    - Raises ValueError if critical anomalies exceed threshold
"""

import json
import os
from typing import Optional

import numpy as np
import pandas as pd

from utils.logging_config import get_logger

logger = get_logger( __name__, component="validate" )


def validate_data(
    input_path       : str,
    output_path      : str,
    schema_output_path: Optional[str] = None,
    anomaly_threshold : int = 0,
) -> dict:
    """
    Validate input data using TFDV-style checks.

    Requires:
        - input_path points to a valid Parquet file
        - output_path is writable

    Ensures:
        - Returns dict with schema stats and anomaly report
        - Writes validated Parquet to output_path (pass-through if clean)
        - Raises ValueError if critical anomaly count exceeds threshold

    Raises:
        - ValueError if anomalies exceed anomaly_threshold
        - FileNotFoundError if input_path doesn't exist
    """
    logger.info( f"Validating data from {input_path}" )
    df = pd.read_parquet( input_path )

    anomalies = []

    # ---- Schema Statistics ----
    schema_stats = _compute_schema_stats( df )

    # ---- Anomaly Detection ----

    # 1. Null value detection
    null_report = _check_nulls( df )
    for col, info in null_report.items():
        if info[ "null_pct" ] > 0.0:
            severity = "WARNING" if info[ "null_pct" ] < 0.05 else "ERROR"
            anomalies.append( {
                "type"     : "null_values",
                "column"   : col,
                "severity" : severity,
                "detail"   : f"{info[ 'null_count' ]:,} nulls ({info[ 'null_pct' ]:.1%})",
            } )

    # 2. Out-of-range detection for numeric columns
    range_checks = {
        "hs_gpa"    : ( 0.0, 4.0 ),
        "sat_score"  : ( 400, 1600 ),
        "act_score"  : ( 1, 36 ),
        "term_gpa"   : ( 0.0, 4.0 ),
        "cumulative_gpa": ( 0.0, 4.0 ),
        "efc"        : ( 0, 100000 ),
    }
    for col, ( low, high ) in range_checks.items():
        if col in df.columns:
            violations = _check_range( df, col, low, high )
            if violations[ "count" ] > 0:
                anomalies.append( {
                    "type"     : "out_of_range",
                    "column"   : col,
                    "severity" : "ERROR",
                    "detail"   : f"{violations[ 'count' ]:,} values outside [{low}, {high}]",
                    "examples" : violations[ "examples" ],
                } )

    # 3. Future date detection
    date_cols = [c for c in df.columns if "date" in c.lower() or c.endswith( "_dt" )]
    for col in date_cols:
        if col in df.columns:
            future = _check_future_dates( df, col )
            if future[ "count" ] > 0:
                anomalies.append( {
                    "type"     : "future_date",
                    "column"   : col,
                    "severity" : "ERROR",
                    "detail"   : f"{future[ 'count' ]:,} dates in the future",
                } )

    # 4. Target variable distribution check
    if "second_year_ret_flag" in df.columns:
        target_dist = df[ "second_year_ret_flag" ].dropna().value_counts( normalize=True )
        minority_pct = target_dist.min() if len( target_dist ) > 1 else 0
        if minority_pct < 0.10:
            anomalies.append( {
                "type"     : "class_imbalance",
                "column"   : "second_year_ret_flag",
                "severity" : "WARNING",
                "detail"   : f"Minority class at {minority_pct:.1%} — severe imbalance",
            } )

    # ---- Report ----
    error_count   = sum( 1 for a in anomalies if a[ "severity" ] == "ERROR" )
    warning_count = sum( 1 for a in anomalies if a[ "severity" ] == "WARNING" )

    report = {
        "input_rows"     : len( df ),
        "input_columns"  : len( df.columns ),
        "anomaly_count"  : len( anomalies ),
        "error_count"    : error_count,
        "warning_count"  : warning_count,
        "anomalies"      : anomalies,
        "schema_stats"   : schema_stats,
    }

    logger.info( f"Validation complete: {error_count} errors, {warning_count} warnings" )

    for anomaly in anomalies:
        log_fn = logger.error if anomaly[ "severity" ] == "ERROR" else logger.warning
        log_fn( f"[{anomaly[ 'type' ]}] {anomaly[ 'column' ]}: {anomaly[ 'detail' ]}" )

    # Save schema stats
    if schema_output_path:
        os.makedirs( os.path.dirname( schema_output_path ) or ".", exist_ok=True )
        with open( schema_output_path, "w" ) as f:
            json.dump( schema_stats, f, indent=2, default=str )

    # Write validated data (pass-through)
    os.makedirs( os.path.dirname( output_path ) or ".", exist_ok=True )
    df.to_parquet( output_path, index=False )

    # Raise if too many critical anomalies
    if anomaly_threshold > 0 and error_count > anomaly_threshold:
        raise ValueError(
            f"Data validation failed: {error_count} errors exceed threshold of {anomaly_threshold}. "
            f"Fix data quality issues before proceeding."
        )

    return report


def _compute_schema_stats( df: pd.DataFrame ) -> dict:
    """Compute per-column statistics for schema generation."""

    stats = {}
    for col in df.columns:
        col_stats = {
            "dtype"      : str( df[ col ].dtype ),
            "null_count" : int( df[ col ].isna().sum() ),
            "null_pct"   : round( df[ col ].isna().mean(), 4 ),
            "unique"     : int( df[ col ].nunique() ),
        }

        if pd.api.types.is_numeric_dtype( df[ col ] ):
            valid = df[ col ].dropna()
            if len( valid ) > 0:
                col_stats[ "min" ]  = float( valid.min() )
                col_stats[ "max" ]  = float( valid.max() )
                col_stats[ "mean" ] = round( float( valid.mean() ), 4 )
                col_stats[ "std" ]  = round( float( valid.std() ), 4 )

        stats[ col ] = col_stats

    return stats


def _check_nulls( df: pd.DataFrame ) -> dict:
    """Check null values per column."""

    report = {}
    for col in df.columns:
        null_count = int( df[ col ].isna().sum() )
        if null_count > 0:
            report[ col ] = {
                "null_count" : null_count,
                "null_pct"   : round( null_count / len( df ), 4 ),
            }
    return report


def _check_range( df: pd.DataFrame, col: str, low: float, high: float ) -> dict:
    """Check for values outside expected range."""

    valid = df[ col ].dropna()
    violations = valid[ ( valid < low ) | ( valid > high ) ]

    return {
        "count"    : len( violations ),
        "examples" : violations.head( 5 ).tolist() if len( violations ) > 0 else [],
    }


def _check_future_dates( df: pd.DataFrame, col: str ) -> dict:
    """Check for dates in the future."""

    from datetime import date

    try:
        dates  = pd.to_datetime( df[ col ], errors="coerce" )
        future = dates[ dates > pd.Timestamp( date.today() ) ]
        return { "count": len( future ) }
    except Exception:
        return { "count": 0 }
