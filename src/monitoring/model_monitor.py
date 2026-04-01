"""
Model monitoring: Drift detection, skew detection, prediction logging.

Implements Vertex AI Model Monitoring patterns locally and provides
hooks for live GCP integration.

Demonstrates Failure & Recovery Testing and Observability competencies.

Requires:
    - Training data statistics (from validate stage schema)
    - Prediction log (from deploy stage)

Ensures:
    - Detects data drift (feature distribution shift)
    - Detects prediction drift (output distribution shift)
    - Detects training-serving skew
    - Triggers alerts when thresholds exceeded
"""

import json
import os
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from utils.logging_config import get_logger

logger = get_logger( __name__, component="model_monitor" )


def monitor_drift(
    training_data_path   : str,
    serving_data_path    : str,
    output_dir           : str,
    target_column        : str = "second_year_ret_flag",
    drift_threshold_js   : float = 0.1,
    skew_threshold       : float = 0.1,
) -> dict:
    """
    Compare training and serving data distributions for drift.

    Requires:
        - training_data_path: Parquet from pipeline training stage
        - serving_data_path: Parquet from deploy predictions or live log

    Ensures:
        - Returns drift report with per-feature JS divergence
        - Flags features exceeding drift_threshold_js
        - Flags prediction distribution skew
    """
    logger.info( "Computing drift metrics..." )

    train_df = pd.read_parquet( training_data_path )
    serve_df = pd.read_parquet( serving_data_path )

    os.makedirs( output_dir, exist_ok=True )

    # Get numeric columns common to both
    train_numeric = train_df.select_dtypes( include=[np.number] )
    serve_numeric = serve_df.select_dtypes( include=[np.number] )
    common_cols   = list( set( train_numeric.columns ) & set( serve_numeric.columns ) )
    common_cols   = [c for c in common_cols if c != target_column and c != "student_id"]

    # ---- Feature Drift (Jensen-Shannon Divergence) ----
    feature_drift = {}
    drifted_features = []

    for col in common_cols:
        train_vals = train_numeric[ col ].dropna()
        serve_vals = serve_numeric[ col ].dropna()

        if len( train_vals ) < 10 or len( serve_vals ) < 10:
            continue

        js_div = _jensen_shannon_divergence( train_vals, serve_vals )
        feature_drift[ col ] = {
            "js_divergence" : round( js_div, 6 ),
            "drifted"       : js_div > drift_threshold_js,
            "train_mean"    : round( float( train_vals.mean() ), 4 ),
            "serve_mean"    : round( float( serve_vals.mean() ), 4 ),
            "train_std"     : round( float( train_vals.std() ), 4 ),
            "serve_std"     : round( float( serve_vals.std() ), 4 ),
        }

        if js_div > drift_threshold_js:
            drifted_features.append( ( col, js_div ) )
            logger.warning( f"  DRIFT: {col} JS={js_div:.4f} > threshold {drift_threshold_js}" )

    # ---- Prediction Drift ----
    prediction_drift = {}
    if "predicted_class" in serve_df.columns and target_column in train_df.columns:
        train_dist = train_df[ target_column ].value_counts( normalize=True ).to_dict()
        serve_dist = serve_df[ "predicted_class" ].value_counts( normalize=True ).to_dict()

        pred_js = _jensen_shannon_divergence_discrete( train_dist, serve_dist )
        prediction_drift = {
            "js_divergence"     : round( pred_js, 6 ),
            "drifted"           : pred_js > drift_threshold_js,
            "training_distribution" : {str( k ): round( v, 4 ) for k, v in train_dist.items()},
            "serving_distribution"  : {str( k ): round( v, 4 ) for k, v in serve_dist.items()},
        }

    # ---- Training-Serving Skew ----
    skew_report = {}
    for col in common_cols[ :20 ]:  # Top 20 features
        train_vals = train_numeric[ col ].dropna()
        serve_vals = serve_numeric[ col ].dropna()

        if len( train_vals ) < 10 or len( serve_vals ) < 10:
            continue

        # KS test for distribution difference
        ks_stat, ks_pvalue = scipy_stats.ks_2samp( train_vals, serve_vals )
        skew_report[ col ] = {
            "ks_statistic" : round( ks_stat, 6 ),
            "ks_pvalue"    : round( ks_pvalue, 6 ),
            "skewed"       : ks_stat > skew_threshold,
        }

    report = {
        "features_analyzed"   : len( common_cols ),
        "drifted_features"    : len( drifted_features ),
        "drift_threshold"     : drift_threshold_js,
        "feature_drift"       : feature_drift,
        "prediction_drift"    : prediction_drift,
        "training_serving_skew": skew_report,
        "alert_triggered"     : len( drifted_features ) > 0 or prediction_drift.get( "drifted", False ),
    }

    report_path = os.path.join( output_dir, "drift_report.json" )
    with open( report_path, "w" ) as f:
        json.dump( report, f, indent=2, default=str )

    logger.info(
        f"Drift analysis complete: {len( drifted_features )}/{len( common_cols )} features drifted, "
        f"prediction drift={'YES' if prediction_drift.get( 'drifted' ) else 'NO'}"
    )

    return report


def _jensen_shannon_divergence( p_vals: pd.Series, q_vals: pd.Series, n_bins: int = 50 ) -> float:
    """
    Compute Jensen-Shannon divergence between two continuous distributions.

    Uses histogram binning to convert continuous values to discrete distributions.
    """
    # Create common bin edges
    all_vals = np.concatenate( [p_vals.values, q_vals.values] )
    bin_edges = np.histogram_bin_edges( all_vals, bins=n_bins )

    p_hist, _ = np.histogram( p_vals, bins=bin_edges, density=True )
    q_hist, _ = np.histogram( q_vals, bins=bin_edges, density=True )

    # Add small epsilon to avoid log(0)
    epsilon = 1e-10
    p_hist  = p_hist + epsilon
    q_hist  = q_hist + epsilon

    # Normalize
    p_hist = p_hist / p_hist.sum()
    q_hist = q_hist / q_hist.sum()

    # JS divergence = 0.5 * KL(P||M) + 0.5 * KL(Q||M) where M = (P+Q)/2
    m = 0.5 * ( p_hist + q_hist )
    js = 0.5 * np.sum( p_hist * np.log( p_hist / m ) ) + 0.5 * np.sum( q_hist * np.log( q_hist / m ) )

    return float( js )


def _jensen_shannon_divergence_discrete( p_dist: dict, q_dist: dict ) -> float:
    """Compute JS divergence between two discrete distributions (dicts)."""

    all_keys = set( p_dist.keys() ) | set( q_dist.keys() )
    epsilon  = 1e-10

    p = np.array( [p_dist.get( k, 0 ) + epsilon for k in all_keys] )
    q = np.array( [q_dist.get( k, 0 ) + epsilon for k in all_keys] )

    p = p / p.sum()
    q = q / q.sum()

    m  = 0.5 * ( p + q )
    js = 0.5 * np.sum( p * np.log( p / m ) ) + 0.5 * np.sum( q * np.log( q / m ) )

    return float( js )
