"""
Harmonize component: Column mapping, type alignment, null filling.

Replaces AMPE's generic_harmonize_metadata.py. Simplified because
Meridian owns the schema (no external metadata CSV needed).

Requires:
    - Input Parquet from DLP scan (redacted PII)

Ensures:
    - All columns have consistent dtypes
    - Nulls filled with sentinel values (dates->1900-01-01, ints->-1, floats->-1.0)
    - Duplicate columns/rows removed
"""

import os
from datetime import date

import numpy as np
import pandas as pd

from utils.logging_config import get_logger

logger = get_logger( __name__, component="harmonize" )

# Expected column types (matches BQ schema)
EXPECTED_DTYPES = {
    "student_id"            : "object",
    "gender"                : "object",
    "ethnicity"             : "object",
    "first_generation_flag" : "bool",
    "hs_gpa"                : "float64",
    "sat_score"             : "float64",
    "act_score"             : "float64",
    "home_state"            : "object",
    "campus"                : "object",
    "campus_latitude"       : "float64",
    "campus_longitude"      : "float64",
    "campus_distance_miles" : "float64",
    "hs_latitude"           : "float64",
    "hs_longitude"          : "float64",
    "cohort_year"           : "int64",
    "term_gpa"              : "float64",
    "cumulative_gpa"        : "float64",
    "credits_attempted"     : "float64",
    "credits_earned"        : "float64",
    "course_count"          : "float64",
    "major"                 : "object",
    "major_changed_flag"    : "bool",
    "academic_standing"     : "object",
    "efc"                   : "float64",
    "pell_eligible"         : "bool",
    "total_aid_amount"      : "float64",
    "loan_amount"           : "float64",
    "grant_amount"          : "float64",
    "scholarship_amount"    : "float64",
    "unmet_need"            : "float64",
    "work_study_flag"       : "bool",
    "enrollment_status"     : "object",
    "second_year_ret_flag"  : "float64",
}

# Null sentinel values by dtype family
NULL_SENTINELS = {
    "float64" : -1.0,
    "int64"   : -1,
    "object"  : "unknown",
    "bool"    : False,
}


def harmonize(
    input_path  : str,
    output_path : str,
) -> dict:
    """
    Harmonize data: type alignment, null filling, deduplication.

    Requires:
        - input_path points to valid Parquet

    Ensures:
        - Returns dict with harmonization stats
        - All columns type-aligned per EXPECTED_DTYPES
        - Nulls filled with sentinel values
        - Duplicate rows removed
    """
    logger.info( f"Harmonizing data from {input_path}" )
    df = pd.read_parquet( input_path )

    initial_rows = len( df )
    initial_cols = len( df.columns )

    # 1. Remove duplicate rows
    df = df.drop_duplicates()
    rows_after_dedup = len( df )

    # 2. Remove duplicate columns
    df = df.loc[ :, ~df.columns.duplicated() ]

    # 3. Type coercion
    coerced_cols = []
    for col, expected_dtype in EXPECTED_DTYPES.items():
        if col not in df.columns:
            continue
        try:
            if expected_dtype == "bool":
                df[ col ] = df[ col ].astype( bool )
            elif expected_dtype == "float64":
                df[ col ] = pd.to_numeric( df[ col ], errors="coerce" )
            elif expected_dtype == "int64":
                df[ col ] = pd.to_numeric( df[ col ], errors="coerce" ).astype( "Int64" )
            elif expected_dtype == "object":
                df[ col ] = df[ col ].astype( str ).replace( "nan", np.nan ).replace( "None", np.nan )
            coerced_cols.append( col )
        except Exception as e:
            logger.warning( f"Type coercion failed for {col} -> {expected_dtype}: {e}" )

    # 4. Fill nulls with sentinel values
    filled_cols = []
    for col in df.columns:
        null_count = df[ col ].isna().sum()
        if null_count == 0:
            continue

        dtype_str = str( df[ col ].dtype )
        sentinel  = None

        for dtype_key, sentinel_val in NULL_SENTINELS.items():
            if dtype_key in dtype_str:
                sentinel = sentinel_val
                break

        if sentinel is not None:
            df[ col ] = df[ col ].fillna( sentinel )
            filled_cols.append( ( col, null_count, sentinel ) )
            logger.info( f"  Filled {col}: {null_count:,} nulls -> {sentinel}" )

    # 5. Drop columns not in our expected schema (cleanup merge artifacts)
    known_cols    = set( EXPECTED_DTYPES.keys() ) | {"student_id", "event_type", "event_date", "term"}
    extra_cols    = [c for c in df.columns if c not in known_cols and not c.endswith( ( "_demo", "_fin", "_acad" ) )]
    # Keep extra columns but log them
    if extra_cols:
        logger.info( f"  Extra columns retained: {extra_cols}" )

    os.makedirs( os.path.dirname( output_path ) or ".", exist_ok=True )
    df.to_parquet( output_path, index=False )

    report = {
        "initial_rows"     : initial_rows,
        "rows_after_dedup" : rows_after_dedup,
        "duplicates_removed": initial_rows - rows_after_dedup,
        "columns_coerced"  : len( coerced_cols ),
        "nulls_filled"     : len( filled_cols ),
        "output_rows"      : len( df ),
        "output_columns"   : len( df.columns ),
    }

    logger.info(
        f"Harmonization complete: {report[ 'duplicates_removed' ]} dupes removed, "
        f"{report[ 'nulls_filled' ]} columns null-filled, "
        f"{report[ 'output_rows' ]:,} rows -> {output_path}"
    )

    return report
