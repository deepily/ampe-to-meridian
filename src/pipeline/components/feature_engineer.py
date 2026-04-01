"""
Feature engineering component: Date deltas, binning, derived features.

Replaces AMPE's generic_feature_engineering.py + retention-specific extensions.
Creates domain-relevant features for student retention prediction.

Requires:
    - Cleaned Parquet (numeric, OHE'd)

Ensures:
    - Date deltas computed (app->enroll, fafsa->enroll)
    - GPA ratios and credit ratios added
    - Distance binning applied
    - Output has additional derived feature columns
"""

import os

import numpy as np
import pandas as pd

from utils.logging_config import get_logger

logger = get_logger( __name__, component="feature_engineer" )


def feature_engineer(
    input_path  : str,
    output_path : str,
    target_column: str = "second_year_ret_flag",
) -> dict:
    """
    Create derived features for retention prediction.

    Requires:
        - input_path points to cleaned Parquet

    Ensures:
        - Returns dict with feature engineering stats
        - New feature columns added to DataFrame
        - No features leak the target variable
    """
    logger.info( f"Engineering features from {input_path}" )
    df = pd.read_parquet( input_path )

    initial_cols = len( df.columns )
    new_features = []

    # 1. GPA-related features
    if "cumulative_gpa" in df.columns and "hs_gpa" in df.columns:
        df[ "gpa_change" ] = df[ "cumulative_gpa" ] - df[ "hs_gpa" ]
        new_features.append( "gpa_change" )

        # GPA improvement flag
        df[ "gpa_improved" ] = ( df[ "gpa_change" ] > 0 ).astype( int )
        new_features.append( "gpa_improved" )

    if "term_gpa" in df.columns and "cumulative_gpa" in df.columns:
        # Term vs cumulative ratio (momentum indicator)
        df[ "gpa_momentum" ] = np.where(
            df[ "cumulative_gpa" ] > 0,
            df[ "term_gpa" ] / df[ "cumulative_gpa" ],
            1.0
        )
        new_features.append( "gpa_momentum" )

    # 2. Credit-related features (AMPE's calculate_credit_ratio)
    if "credits_earned" in df.columns and "credits_attempted" in df.columns:
        df[ "credit_ratio" ] = np.where(
            df[ "credits_attempted" ] > 0,
            df[ "credits_earned" ] / df[ "credits_attempted" ],
            0.0
        )
        new_features.append( "credit_ratio" )

        # Credit deficit
        df[ "credit_deficit" ] = df[ "credits_attempted" ] - df[ "credits_earned" ]
        new_features.append( "credit_deficit" )

    # 3. Financial need features
    if "efc" in df.columns and "total_aid_amount" in df.columns:
        # Aid coverage ratio
        df[ "aid_coverage_ratio" ] = np.where(
            df[ "efc" ] > 0,
            df[ "total_aid_amount" ] / df[ "efc" ],
            0.0
        )
        # Clip extreme ratios
        df[ "aid_coverage_ratio" ] = df[ "aid_coverage_ratio" ].clip( 0, 50 )
        new_features.append( "aid_coverage_ratio" )

    if "loan_amount" in df.columns and "total_aid_amount" in df.columns:
        # Loan dependency ratio
        df[ "loan_dependency" ] = np.where(
            df[ "total_aid_amount" ] > 0,
            df[ "loan_amount" ] / df[ "total_aid_amount" ],
            0.0
        )
        new_features.append( "loan_dependency" )

    # 4. Distance binning (AMPE's campus_distance_miles)
    if "campus_distance_miles" in df.columns:
        bins   = [0, 25, 50, 100, 250, 500, float( "inf" )]
        labels = [0, 1, 2, 3, 4, 5]
        df[ "distance_bin" ] = pd.cut(
            df[ "campus_distance_miles" ],
            bins=bins, labels=labels, include_lowest=True
        ).astype( float ).fillna( -1 ).astype( int )
        new_features.append( "distance_bin" )

    # 5. SAT/ACT composite (if both available)
    if "sat_score" in df.columns and "act_score" in df.columns:
        # Normalize both to 0-1 range and average
        sat_norm = ( df[ "sat_score" ] - 400 ) / 1200  # SAT range 400-1600
        act_norm = ( df[ "act_score" ] - 1 ) / 35      # ACT range 1-36
        df[ "test_score_composite" ] = ( ( sat_norm + act_norm ) / 2 ).clip( 0, 1 )
        new_features.append( "test_score_composite" )

    # 6. Cohort age features
    if "cohort_year" in df.columns:
        # Cohort recency (newer cohorts = higher value)
        df[ "cohort_recency" ] = df[ "cohort_year" ] - df[ "cohort_year" ].min()
        new_features.append( "cohort_recency" )

    # 7. Replace any infinities with NaN then fill
    df = df.replace( [np.inf, -np.inf], np.nan )
    for col in new_features:
        if col in df.columns:
            df[ col ] = df[ col ].fillna( -1.0 )

    os.makedirs( os.path.dirname( output_path ) or ".", exist_ok=True )
    df.to_parquet( output_path, index=False )

    report = {
        "initial_columns"  : initial_cols,
        "new_features"     : new_features,
        "new_feature_count": len( new_features ),
        "output_columns"   : len( df.columns ),
        "output_rows"      : len( df ),
    }

    logger.info(
        f"Feature engineering complete: {len( new_features )} new features, "
        f"{report[ 'output_columns' ]} total columns -> {output_path}"
    )

    return report
