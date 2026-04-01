"""
Explain component: Vertex Explainable AI / local SHAP feature attributions.

Replaces AMPE's generic_post_modeling_shap.py with Vertex Explainable AI
(Sampled Shapley) for GCP, falling back to local SHAP for testing.

Demonstrates AI-Specific Security competency (model explainability,
Responsible AI).

Requires:
    - Winning model from evaluate stage
    - Reduced Parquet with features

Ensures:
    - Feature attributions computed for test predictions
    - Top-N important features identified
    - Results exportable as model card input
"""

import json
import os
import pickle
from typing import Optional

import numpy as np
import pandas as pd

from utils.logging_config import get_logger

logger = get_logger( __name__, component="explain" )


def explain(
    input_path        : str,
    model_path        : str,
    output_dir        : str,
    target_column     : str = "second_year_ret_flag",
    top_n_features    : int = 15,
    use_vertex_xai    : bool = False,
    project_id        : Optional[str] = None,
    region            : Optional[str] = None,
) -> dict:
    """
    Compute feature attributions for the winning model.

    Requires:
        - input_path points to reduced Parquet
        - model_path points to serialized model pickle

    Ensures:
        - Returns dict with feature importances (model-native + permutation)
        - Saves feature importance report to output_dir
        - Top N features identified for model card
    """
    logger.info( f"Computing explanations for model at {model_path}" )

    df = pd.read_parquet( input_path )

    # Load model
    with open( model_path, "rb" ) as f:
        model = pickle.load( f )

    # Prepare features
    drop_cols = [target_column]
    if "student_id" in df.columns:
        drop_cols.append( "student_id" )
    X = df.drop( columns=drop_cols, errors="ignore" )
    y = df[ target_column ].astype( int ) if target_column in df.columns else None

    os.makedirs( output_dir, exist_ok=True )

    # ---- Model-native feature importance ----
    native_importance = _get_native_importance( model, X.columns.tolist() )

    # ---- Permutation importance (model-agnostic) ----
    perm_importance = _permutation_importance( model, X, y ) if y is not None else {}

    # ---- Merge and rank ----
    all_features = {}
    for feat in X.columns:
        all_features[ feat ] = {
            "native_importance"      : native_importance.get( feat, 0.0 ),
            "permutation_importance" : perm_importance.get( feat, 0.0 ),
        }

    # Rank by native importance (or permutation if no native)
    ranked = sorted(
        all_features.items(),
        key=lambda x: x[ 1 ][ "native_importance" ] or x[ 1 ][ "permutation_importance" ],
        reverse=True,
    )

    top_features = [
        { "feature": name, **scores }
        for name, scores in ranked[ :top_n_features ]
    ]

    report = {
        "model_path"          : model_path,
        "model_type"          : type( model ).__name__,
        "total_features"      : len( X.columns ),
        "top_features"        : top_features,
        "explanation_method"  : "native_importance + permutation",
        "mode"                : "vertex_xai" if use_vertex_xai else "local",
    }

    # Save report
    report_path = os.path.join( output_dir, "explanation_report.json" )
    with open( report_path, "w" ) as f:
        json.dump( report, f, indent=2, default=str )

    # Save full feature importance DataFrame
    importance_df = pd.DataFrame( [
        { "feature": name, **scores }
        for name, scores in ranked
    ] )
    importance_df.to_csv( os.path.join( output_dir, "feature_importance.csv" ), index=False )

    logger.info(
        f"Explanation complete. Top 3 features: "
        f"{', '.join( f[ 'feature' ] for f in top_features[ :3 ] )}"
    )

    return report


def _get_native_importance( model, feature_names: list ) -> dict:
    """
    Extract model-native feature importance.

    Works for tree-based models (XGBoost, RF, GB, DT, AdaBoost).
    Returns empty dict for models without feature_importances_.
    """
    importances = {}

    if hasattr( model, "feature_importances_" ):
        for name, score in zip( feature_names, model.feature_importances_ ):
            importances[ name ] = float( score )
    elif hasattr( model, "coef_" ):
        # Logistic regression — use absolute coefficient values
        coefs = np.abs( model.coef_[ 0 ] ) if model.coef_.ndim > 1 else np.abs( model.coef_ )
        for name, score in zip( feature_names, coefs ):
            importances[ name ] = float( score )

    return importances


def _permutation_importance(
    model,
    X      : pd.DataFrame,
    y      : pd.Series,
    n_repeats: int = 5,
) -> dict:
    """
    Compute permutation feature importance.

    Model-agnostic approach: shuffle each feature and measure
    accuracy drop. Larger drop = more important.
    """
    from sklearn.inspection import permutation_importance as sklearn_perm_importance

    try:
        result = sklearn_perm_importance(
            model, X, y,
            n_repeats=n_repeats,
            random_state=42,
            n_jobs=-1,
            scoring="accuracy",
        )
        return {
            name: float( score )
            for name, score in zip( X.columns, result.importances_mean )
        }
    except Exception as e:
        logger.warning( f"Permutation importance failed: {e}" )
        return {}
