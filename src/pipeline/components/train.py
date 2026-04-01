"""
Train component: Multi-algorithm model training with SMOTE.

Preserves AMPE's GenericModel pattern — trains 6 algorithms with
configurable SMOTE strategies for class imbalance handling.

Replaces AMPE's generic_model_build_*.py extensions and GenericModel class.

Requires:
    - Reduced Parquet (fully numeric, dimensionality-reduced)
    - Target column present

Ensures:
    - Trains all configured algorithms x SMOTE strategies
    - Returns dict of trained models with metrics
    - Serializes models to output directory
"""

import json
import os
import pickle
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import (
    AdaBoostClassifier,
    GradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier

from utils.logging_config import get_logger

logger = get_logger( __name__, component="train" )

# ---- Algorithm Registry ----

ALGORITHMS = {
    "xgboost"              : None,  # Lazy import to avoid hard dependency
    "random_forest"        : lambda: RandomForestClassifier( n_estimators=100, random_state=42, n_jobs=-1 ),
    "logistic_regression"  : lambda: LogisticRegression( max_iter=1000, random_state=42 ),
    "adaboost"             : lambda: AdaBoostClassifier( n_estimators=50, random_state=42 ),
    "decision_tree"        : lambda: DecisionTreeClassifier( max_depth=10, random_state=42 ),
    "gradient_boosting"    : lambda: GradientBoostingClassifier( n_estimators=100, random_state=42 ),
}

# ---- SMOTE Strategy Registry ----

SMOTE_STRATEGIES = {
    "none"      : None,
    "smote"     : None,  # Lazy import
    "adasyn"    : None,
    "smotetomek": None,
    "smoteenn"  : None,
}


def _get_xgboost():
    """Lazy import XGBoost."""
    from xgboost import XGBClassifier
    return XGBClassifier(
        n_estimators=100, max_depth=6, learning_rate=0.1,
        random_state=42, use_label_encoder=False, eval_metric="logloss",
    )


def _get_smote_algorithm( strategy: str ):
    """Get SMOTE resampler by strategy name."""
    if strategy == "none":
        return None

    from imblearn.over_sampling import ADASYN, SMOTE
    from imblearn.combine import SMOTETomek, SMOTEENN

    registry = {
        "smote"      : lambda: SMOTE( random_state=42 ),
        "adasyn"     : lambda: ADASYN( random_state=42 ),
        "smotetomek" : lambda: SMOTETomek( random_state=42 ),
        "smoteenn"   : lambda: SMOTEENN( random_state=42 ),
    }

    factory = registry.get( strategy )
    if factory is None:
        raise ValueError( f"Unknown SMOTE strategy: {strategy}" )
    return factory()


def train(
    input_path        : str,
    output_dir        : str,
    target_column     : str = "second_year_ret_flag",
    algorithms        : list = None,
    smote_strategies  : list = None,
    test_size         : float = 0.2,
    competition_metric: str = "tn_rate",
) -> dict:
    """
    Train multiple algorithms with SMOTE strategies and select the best.

    Requires:
        - input_path points to reduced numeric Parquet
        - target_column exists in DataFrame
        - algorithms is a list of algorithm names from ALGORITHMS registry

    Ensures:
        - Returns dict with all model results and the competition winner
        - Models serialized as pickle files in output_dir
        - Metrics include accuracy, AUC, precision, recall, F1, confusion matrix
    """
    if algorithms is None:
        algorithms = ["xgboost", "random_forest", "logistic_regression"]
    if smote_strategies is None:
        smote_strategies = ["none", "smote"]

    logger.info( f"Training {len( algorithms )} algorithms x {len( smote_strategies )} SMOTE strategies" )

    df = pd.read_parquet( input_path )

    # Separate features and target
    id_col = "student_id" if "student_id" in df.columns else None
    drop_cols = [target_column]
    if id_col:
        drop_cols.append( id_col )

    X = df.drop( columns=drop_cols, errors="ignore" )
    y = df[ target_column ].astype( int )

    # Train-test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=42, stratify=y
    )

    logger.info( f"Split: {len( X_train ):,} train, {len( X_test ):,} test" )
    logger.info( f"Class distribution — train: {dict( y_train.value_counts() )}, test: {dict( y_test.value_counts() )}" )

    os.makedirs( output_dir, exist_ok=True )

    # ---- Train all combinations ----
    all_results = []

    for algo_name in algorithms:
        for strategy in smote_strategies:
            result = _train_single(
                algo_name, strategy,
                X_train.copy(), X_test.copy(),
                y_train.copy(), y_test.copy(),
                output_dir,
            )
            all_results.append( result )

            logger.info(
                f"  {algo_name}/{strategy}: "
                f"accuracy={result[ 'accuracy' ]:.3f}, "
                f"auc={result[ 'auc' ]:.3f}, "
                f"tn_rate={result[ 'tn_rate' ]:.3f}, "
                f"tp_rate={result[ 'tp_rate' ]:.3f}"
            )

    # ---- Model Competition (AMPE pattern) ----
    winner = _select_winner( all_results, competition_metric )

    report = {
        "algorithms_trained"  : len( algorithms ),
        "smote_strategies"    : smote_strategies,
        "total_models"        : len( all_results ),
        "all_results"         : all_results,
        "winner"              : winner,
        "test_size"           : test_size,
        "train_rows"          : len( X_train ),
        "test_rows"           : len( X_test ),
        "feature_count"       : len( X.columns ),
    }

    # Save report
    report_path = os.path.join( output_dir, "training_report.json" )
    with open( report_path, "w" ) as f:
        # Filter out non-serializable items
        serializable = {k: v for k, v in report.items() if k != "all_results"}
        serializable[ "all_results" ] = [
            {k: v for k, v in r.items() if k != "model_object"}
            for r in all_results
        ]
        json.dump( serializable, f, indent=2, default=str )

    logger.info(
        f"Training complete. Winner: {winner[ 'algorithm' ]}/{winner[ 'smote_strategy' ]} "
        f"({competition_metric}={winner[ competition_metric ]:.3f})"
    )

    return report


def _train_single(
    algo_name  : str,
    strategy   : str,
    X_train    : pd.DataFrame,
    X_test     : pd.DataFrame,
    y_train    : pd.Series,
    y_test     : pd.Series,
    output_dir : str,
) -> dict:
    """Train a single algorithm with a single SMOTE strategy."""

    # Apply SMOTE if requested
    if strategy != "none":
        try:
            resampler = _get_smote_algorithm( strategy )
            X_train, y_train = resampler.fit_resample( X_train, y_train )
        except Exception as e:
            logger.warning( f"SMOTE {strategy} failed: {e}. Using original data." )

    # Get model
    if algo_name == "xgboost":
        model = _get_xgboost()
    else:
        factory = ALGORITHMS.get( algo_name )
        if factory is None:
            raise ValueError( f"Unknown algorithm: {algo_name}" )
        model = factory()

    # Train
    model.fit( X_train, y_train )

    # Predict
    y_pred = model.predict( X_test )
    y_prob = model.predict_proba( X_test )[ :, 1 ] if hasattr( model, "predict_proba" ) else y_pred.astype( float )

    # Metrics
    cm       = confusion_matrix( y_test, y_pred )
    tn, fp, fn, tp = cm.ravel() if cm.shape == ( 2, 2 ) else ( 0, 0, 0, 0 )

    result = {
        "algorithm"      : algo_name,
        "smote_strategy" : strategy,
        "accuracy"       : float( accuracy_score( y_test, y_pred ) ),
        "auc"            : float( roc_auc_score( y_test, y_prob ) ),
        "precision"      : float( precision_score( y_test, y_pred, zero_division=0 ) ),
        "recall"         : float( recall_score( y_test, y_pred, zero_division=0 ) ),
        "f1"             : float( f1_score( y_test, y_pred, zero_division=0 ) ),
        "tp_rate"        : float( tp / ( tp + fn ) ) if ( tp + fn ) > 0 else 0.0,
        "tn_rate"        : float( tn / ( tn + fp ) ) if ( tn + fp ) > 0 else 0.0,
        "confusion_matrix": cm.tolist(),
        "train_rows"     : len( X_train ),
        "model_object"   : model,
    }

    # Serialize model
    model_filename = f"{algo_name}_{strategy}.pkl"
    model_path     = os.path.join( output_dir, model_filename )
    with open( model_path, "wb" ) as f:
        pickle.dump( model, f )
    result[ "model_path" ] = model_path

    return result


def _select_winner( results: list, metric: str ) -> dict:
    """
    Select the winning model by competition metric.

    Preserves AMPE's model competition pattern (compare TP/TN rates).
    """
    if not results:
        return {}

    sorted_results = sorted( results, key=lambda r: r.get( metric, 0 ), reverse=True )
    winner = sorted_results[ 0 ]

    return {
        "algorithm"      : winner[ "algorithm" ],
        "smote_strategy" : winner[ "smote_strategy" ],
        "accuracy"       : winner[ "accuracy" ],
        "auc"            : winner[ "auc" ],
        "tp_rate"        : winner[ "tp_rate" ],
        "tn_rate"        : winner[ "tn_rate" ],
        "f1"             : winner[ "f1" ],
        "model_path"     : winner[ "model_path" ],
    }
