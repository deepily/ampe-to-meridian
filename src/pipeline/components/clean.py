"""
Clean component: Null handling, OHE, constant column removal, string encoding.

Replaces AMPE's generic_data_cleaning_v1_2.py. Configuration-driven
via Pydantic instead of INI keys.

Requires:
    - Harmonized Parquet (types aligned, nulls filled)

Ensures:
    - Constant columns removed
    - Categorical strings one-hot encoded (up to max_categories)
    - Remaining string columns dropped
    - Output is fully numeric (ready for modeling)
"""

import os

import numpy as np
import pandas as pd

from utils.logging_config import get_logger

logger = get_logger( __name__, component="clean" )

# Columns to always skip in encoding/dropping
SKIP_COLUMNS = {"student_id", "event_type", "event_date", "term"}

# Columns that are constant by design (keep them)
CONSTANT_SKIP = {"campus_longitude", "campus_latitude"}


def clean(
    input_path     : str,
    output_path    : str,
    target_column  : str = "second_year_ret_flag",
    max_categories : int = 50,
    drop_strings   : bool = True,
    ohe_enabled    : bool = True,
) -> dict:
    """
    Clean data: remove constants, OHE categoricals, drop strings.

    Requires:
        - input_path points to harmonized Parquet
        - target_column exists in the DataFrame

    Ensures:
        - Returns dict with cleaning stats
        - Output DataFrame is fully numeric (except student_id)
        - Constant columns removed (except CONSTANT_SKIP)
        - Categoricals OHE'd if <= max_categories unique values
    """
    logger.info( f"Cleaning data from {input_path}" )
    df = pd.read_parquet( input_path )

    initial_cols = len( df.columns )
    dropped_cols = []

    # 1. Drop columns that shouldn't be features
    cols_to_drop = [c for c in SKIP_COLUMNS if c in df.columns and c != "student_id"]
    if cols_to_drop:
        df = df.drop( columns=cols_to_drop )
        dropped_cols.extend( cols_to_drop )

    # 2. Remove constant columns (single unique value)
    for col in df.columns:
        if col in CONSTANT_SKIP or col == target_column or col == "student_id":
            continue
        if df[ col ].nunique() <= 1:
            df = df.drop( columns=[col] )
            dropped_cols.append( col )
            logger.info( f"  Dropped constant column: {col}" )

    # 3. One-hot encode categorical strings
    ohe_cols = []
    if ohe_enabled:
        string_cols = df.select_dtypes( include=["object"] ).columns.tolist()
        string_cols = [c for c in string_cols if c != "student_id"]

        for col in string_cols:
            n_unique = df[ col ].nunique()
            if n_unique <= max_categories:
                dummies = pd.get_dummies( df[ col ], prefix=col, prefix_sep="_" )
                # Convert boolean dummies to int
                dummies = dummies.astype( int )
                df = pd.concat( [df.drop( columns=[col] ), dummies], axis=1 )
                ohe_cols.append( ( col, n_unique ) )
                logger.info( f"  OHE: {col} ({n_unique} categories)" )
            else:
                logger.info( f"  Skipped OHE for {col} ({n_unique} categories > {max_categories})" )

    # 4. Drop remaining string columns (except student_id)
    if drop_strings:
        remaining_strings = df.select_dtypes( include=["object"] ).columns.tolist()
        remaining_strings = [c for c in remaining_strings if c != "student_id"]
        if remaining_strings:
            df = df.drop( columns=remaining_strings )
            dropped_cols.extend( remaining_strings )
            logger.info( f"  Dropped remaining strings: {remaining_strings}" )

    # 5. Convert booleans to int
    bool_cols = df.select_dtypes( include=["bool"] ).columns.tolist()
    for col in bool_cols:
        df[ col ] = df[ col ].astype( int )

    os.makedirs( os.path.dirname( output_path ) or ".", exist_ok=True )
    df.to_parquet( output_path, index=False )

    report = {
        "initial_columns"    : initial_cols,
        "output_columns"     : len( df.columns ),
        "dropped_columns"    : dropped_cols,
        "ohe_columns"        : [c for c, _ in ohe_cols],
        "ohe_total_dummies"  : sum( n for _, n in ohe_cols ),
        "output_rows"        : len( df ),
    }

    logger.info(
        f"Cleaning complete: {len( dropped_cols )} cols dropped, "
        f"{len( ohe_cols )} cols OHE'd, "
        f"{report[ 'output_columns' ]} output columns -> {output_path}"
    )

    return report
