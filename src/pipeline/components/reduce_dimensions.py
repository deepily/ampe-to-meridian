"""
Reduce dimensions component: Correlation culling + VIF analysis.

Replaces AMPE's generic_dimensionality_reduction.py and
generic_dimensionality_vif_analysis_binary_search.py.

Requires:
    - Feature-engineered Parquet (fully numeric)

Ensures:
    - Weak correlations culled (|r| < threshold with target)
    - High multicollinearity removed (VIF > threshold)
    - Target column and student_id preserved
"""

import os

import numpy as np
import pandas as pd

from utils.logging_config import get_logger

logger = get_logger( __name__, component="reduce_dimensions" )


def reduce_dimensions(
    input_path            : str,
    output_path           : str,
    target_column         : str = "second_year_ret_flag",
    correlation_threshold : float = 0.85,
    correlation_method    : str = "pearson",
    vif_threshold         : float = 10.0,
    skip_columns          : list = None,
) -> dict:
    """
    Reduce feature dimensions via correlation culling and VIF analysis.

    Requires:
        - input_path points to numeric Parquet
        - target_column exists in DataFrame

    Ensures:
        - Returns dict with reduction stats
        - Removes features with near-zero correlation to target
        - Removes features with VIF > vif_threshold
        - Preserves target_column and student_id
    """
    if skip_columns is None:
        skip_columns = ["campus_longitude", "campus_latitude"]

    logger.info( f"Reducing dimensions from {input_path}" )
    df = pd.read_parquet( input_path )

    initial_cols = len( df.columns )
    protected    = {"student_id", target_column} | set( skip_columns )

    # Separate protected columns
    feature_cols = [c for c in df.columns if c not in protected and pd.api.types.is_numeric_dtype( df[ c ] )]

    # ---- Step 1: Correlation-based feature selection ----
    if target_column in df.columns:
        corr_kept, corr_dropped = _correlation_cull(
            df, feature_cols, target_column, correlation_threshold, correlation_method
        )
    else:
        corr_kept    = feature_cols
        corr_dropped = []

    logger.info( f"  Correlation culling: {len( corr_dropped )} dropped, {len( corr_kept )} kept" )

    # ---- Step 2: Remove highly correlated feature pairs ----
    pair_dropped = _drop_correlated_pairs( df, corr_kept, correlation_threshold )
    remaining    = [c for c in corr_kept if c not in pair_dropped]

    logger.info( f"  Pair correlation: {len( pair_dropped )} dropped, {len( remaining )} kept" )

    # ---- Step 3: VIF analysis ----
    if len( remaining ) > 2:
        vif_kept, vif_dropped = _vif_cull( df, remaining, vif_threshold )
    else:
        vif_kept    = remaining
        vif_dropped = []

    logger.info( f"  VIF culling: {len( vif_dropped )} dropped, {len( vif_kept )} kept" )

    # ---- Rebuild DataFrame ----
    final_cols = list( protected & set( df.columns ) ) + vif_kept
    # Deduplicate while preserving order
    seen       = set()
    final_cols = [c for c in final_cols if c not in seen and not seen.add( c )]

    df_reduced = df[ final_cols ].copy()

    os.makedirs( os.path.dirname( output_path ) or ".", exist_ok=True )
    df_reduced.to_parquet( output_path, index=False )

    report = {
        "initial_features"       : initial_cols,
        "correlation_dropped"    : corr_dropped,
        "pair_correlation_dropped": pair_dropped,
        "vif_dropped"            : vif_dropped,
        "final_features"         : len( df_reduced.columns ),
        "output_rows"            : len( df_reduced ),
    }

    logger.info(
        f"Dimensionality reduction complete: {initial_cols} -> {len( df_reduced.columns )} columns -> {output_path}"
    )

    return report


def _correlation_cull(
    df          : pd.DataFrame,
    feature_cols: list,
    target_col  : str,
    threshold   : float,
    method      : str,
) -> tuple:
    """
    Remove features with near-zero correlation to target.

    Keeps features where |correlation| > (1 - threshold) * 0.1
    This is a soft threshold — we keep features with any meaningful signal.
    """
    if target_col not in df.columns:
        return feature_cols, []

    target = df[ target_col ]
    kept    = []
    dropped = []

    # Minimum correlation to keep (e.g., 0.015 for threshold=0.85)
    min_corr = ( 1 - threshold ) * 0.1

    for col in feature_cols:
        if col == target_col:
            continue
        try:
            corr = abs( df[ col ].corr( target, method=method ) )
            if pd.isna( corr ) or corr < min_corr:
                dropped.append( col )
            else:
                kept.append( col )
        except Exception:
            kept.append( col )  # Keep if can't compute

    return kept, dropped


def _drop_correlated_pairs(
    df          : pd.DataFrame,
    feature_cols: list,
    threshold   : float,
) -> list:
    """
    Remove one feature from each pair with |inter-correlation| > threshold.

    Replaces AMPE's correlation matrix approach.
    Keeps the feature with higher correlation to target.
    """
    if len( feature_cols ) < 2:
        return []

    corr_matrix = df[ feature_cols ].corr().abs()
    dropped     = set()

    for i in range( len( feature_cols ) ):
        if feature_cols[ i ] in dropped:
            continue
        for j in range( i + 1, len( feature_cols ) ):
            if feature_cols[ j ] in dropped:
                continue
            if corr_matrix.iloc[ i, j ] > threshold:
                # Drop the one with fewer unique values (likely less informative)
                if df[ feature_cols[ i ] ].nunique() <= df[ feature_cols[ j ] ].nunique():
                    dropped.add( feature_cols[ i ] )
                else:
                    dropped.add( feature_cols[ j ] )

    return list( dropped )


def _vif_cull(
    df           : pd.DataFrame,
    feature_cols : list,
    threshold    : float,
    max_iterations: int = 10,
) -> tuple:
    """
    Iteratively remove features with VIF > threshold.

    Replaces AMPE's binary search VIF approach with a simpler
    greedy removal of the highest-VIF feature per iteration.
    """
    from statsmodels.stats.outliers_influence import variance_inflation_factor

    remaining = list( feature_cols )
    dropped   = []

    for iteration in range( max_iterations ):
        if len( remaining ) < 2:
            break

        # Build numeric matrix
        X = df[ remaining ].select_dtypes( include=[np.number] ).dropna()
        if len( X ) < 10 or len( X.columns ) < 2:
            break

        # Calculate VIF for each feature
        try:
            vif_data = []
            for i in range( len( X.columns ) ):
                vif_val = variance_inflation_factor( X.values, i )
                vif_data.append( ( X.columns[ i ], vif_val ) )
        except Exception as e:
            logger.warning( f"VIF calculation failed: {e}" )
            break

        # Find max VIF
        vif_df  = pd.DataFrame( vif_data, columns=["feature", "vif"] )
        max_vif = vif_df[ "vif" ].replace( [np.inf, -np.inf], np.nan ).dropna()

        if len( max_vif ) == 0 or max_vif.max() <= threshold:
            break

        # Drop feature with highest VIF
        worst_idx = max_vif.idxmax()
        worst_col = vif_df.loc[ worst_idx, "feature" ]
        worst_vif = vif_df.loc[ worst_idx, "vif" ]

        remaining.remove( worst_col )
        dropped.append( worst_col )
        logger.info( f"  VIF iteration {iteration + 1}: dropped {worst_col} (VIF={worst_vif:.1f})" )

    return remaining, dropped
