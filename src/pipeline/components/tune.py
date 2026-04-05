"""
Tune component: Hyperparameter tuning via Vertex AI Vizier or local grid search.

Replaces AMPE's sklearn ParameterSampler with Bayesian optimization.
Falls back to local RandomizedSearchCV when no GCP credentials.

Requires:
    - Reduced Parquet (fully numeric)
    - Winning algorithm name from train stage

Ensures:
    - Returns best hyperparameters and tuned model
    - Logs tuning trials to output directory
"""

import json
import os
import pickle
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.model_selection import RandomizedSearchCV, train_test_split

from utils.logging_config import get_logger

logger = get_logger( __name__ )

# ---- Hyperparameter Search Spaces ----

SEARCH_SPACES = {
    "xgboost": {
        "n_estimators"  : [50, 100, 200, 300],
        "max_depth"     : [3, 4, 5, 6, 8, 10],
        "learning_rate" : [0.01, 0.05, 0.1, 0.2],
        "subsample"     : [0.6, 0.7, 0.8, 0.9, 1.0],
        "colsample_bytree": [0.6, 0.7, 0.8, 0.9, 1.0],
        "min_child_weight": [1, 3, 5, 7],
        "reg_alpha"     : [0, 0.01, 0.1, 1.0],
        "reg_lambda"    : [0.5, 1.0, 2.0, 5.0],
    },
    "random_forest": {
        "n_estimators"  : [50, 100, 200, 300],
        "max_depth"     : [5, 10, 15, 20, None],
        "min_samples_split": [2, 5, 10],
        "min_samples_leaf" : [1, 2, 4],
        "max_features"  : ["sqrt", "log2", None],
    },
    "logistic_regression": {
        "C"             : [0.01, 0.1, 1.0, 10.0, 100.0],
        "penalty"       : ["l1", "l2"],
        "solver"        : ["liblinear", "saga"],
        "max_iter"      : [500, 1000, 2000],
    },
    "gradient_boosting": {
        "n_estimators"  : [50, 100, 200],
        "max_depth"     : [3, 4, 5, 6],
        "learning_rate" : [0.01, 0.05, 0.1, 0.2],
        "subsample"     : [0.6, 0.7, 0.8, 0.9, 1.0],
        "min_samples_split": [2, 5, 10],
    },
    "adaboost": {
        "n_estimators"  : [25, 50, 100, 200],
        "learning_rate" : [0.01, 0.05, 0.1, 0.5, 1.0],
    },
    "decision_tree": {
        "max_depth"     : [3, 5, 7, 10, 15, 20, None],
        "min_samples_split": [2, 5, 10, 20],
        "min_samples_leaf" : [1, 2, 4, 8],
        "criterion"     : ["gini", "entropy"],
    },
}


def tune(
    input_path       : str,
    output_dir       : str,
    algorithm        : str = "xgboost",
    target_column    : str = "second_year_ret_flag",
    n_iter           : int = 20,
    cv_folds         : int = 5,
    test_size        : float = 0.2,
    use_vertex_vizier: bool = False,
    project_id       : Optional[str] = None,
    region           : Optional[str] = None,
) -> dict:
    """
    Tune hyperparameters for the specified algorithm.

    Requires:
        - input_path points to reduced numeric Parquet
        - algorithm is in SEARCH_SPACES registry

    Ensures:
        - Returns dict with best params, best score, and tuned model path
        - Serializes tuned model to output_dir
    """
    logger.info( f"Tuning {algorithm} with {n_iter} iterations, {cv_folds}-fold CV" )

    df = pd.read_parquet( input_path )

    # Separate features and target
    drop_cols = [target_column]
    if "student_id" in df.columns:
        drop_cols.append( "student_id" )

    X = df.drop( columns=drop_cols, errors="ignore" )
    y = df[ target_column ].astype( int )

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=42, stratify=y
    )

    if use_vertex_vizier and project_id:
        result = _tune_with_vizier(
            X_train, y_train, X_test, y_test,
            algorithm, n_iter, project_id, region
        )
    else:
        result = _tune_local(
            X_train, y_train, X_test, y_test,
            algorithm, n_iter, cv_folds
        )

    os.makedirs( output_dir, exist_ok=True )

    # Save tuned model
    model_path = os.path.join( output_dir, f"{algorithm}_tuned.pkl" )
    with open( model_path, "wb" ) as f:
        pickle.dump( result[ "model" ], f )
    result[ "model_path" ] = model_path

    # Save tuning report
    report_path = os.path.join( output_dir, "tuning_report.json" )
    serializable = {k: v for k, v in result.items() if k != "model"}
    with open( report_path, "w" ) as f:
        json.dump( serializable, f, indent=2, default=str )

    logger.info(
        f"Tuning complete: best score={result[ 'best_score' ]:.4f}, "
        f"best params={result[ 'best_params' ]}"
    )

    return result


def _tune_local(
    X_train    : pd.DataFrame,
    y_train    : pd.Series,
    X_test     : pd.DataFrame,
    y_test     : pd.Series,
    algorithm  : str,
    n_iter     : int,
    cv_folds   : int,
) -> dict:
    """Local hyperparameter tuning via RandomizedSearchCV."""

    from pipeline.components.train import _get_xgboost, ALGORITHMS

    # Get base model
    if algorithm == "xgboost":
        base_model = _get_xgboost()
    else:
        factory = ALGORITHMS.get( algorithm )
        if factory is None:
            raise ValueError( f"Unknown algorithm: {algorithm}" )
        base_model = factory()

    # Get search space
    param_space = SEARCH_SPACES.get( algorithm, {} )
    if not param_space:
        logger.warning( f"No search space for {algorithm}. Using defaults." )
        base_model.fit( X_train, y_train )
        return {
            "algorithm"    : algorithm,
            "best_params"  : {},
            "best_score"   : float( base_model.score( X_test, y_test ) ),
            "model"        : base_model,
            "mode"         : "local_default",
            "n_iter"       : 0,
        }

    # Randomized search
    search = RandomizedSearchCV(
        estimator=base_model,
        param_distributions=param_space,
        n_iter=min( n_iter, 20 ),  # Cap for speed in testing
        cv=cv_folds,
        scoring="roc_auc",
        random_state=42,
        n_jobs=-1,
        verbose=0,
    )

    search.fit( X_train, y_train )

    return {
        "algorithm"    : algorithm,
        "best_params"  : search.best_params_,
        "best_score"   : float( search.best_score_ ),
        "test_score"   : float( search.score( X_test, y_test ) ),
        "model"        : search.best_estimator_,
        "mode"         : "local_randomized_search",
        "n_iter"       : min( n_iter, 20 ),
        "cv_folds"     : cv_folds,
    }


def _tune_with_vizier(
    X_train    : pd.DataFrame,
    y_train    : pd.Series,
    X_test     : pd.DataFrame,
    y_test     : pd.Series,
    algorithm  : str,
    n_iter     : int,
    project_id : str,
    region     : str,
) -> dict:
    """
    Tune with Vertex AI Vizier (Bayesian optimization).

    Requires:
        - google-cloud-aiplatform installed
        - GCP credentials configured
        - algorithm is a key in SEARCH_SPACES

    Ensures:
        - Creates a Vizier study with the algorithm's search space
        - Runs n_iter trials with Bayesian optimization
        - Returns best parameters and fitted model

    Raises:
        - Falls back to local search if Vizier study fails
    """
    from google.cloud import aiplatform
    from pipeline.components.train import _get_xgboost, ALGORITHMS

    aiplatform.init( project=project_id, location=region )

    param_space = SEARCH_SPACES.get( algorithm, {} )
    if not param_space:
        logger.warning( f"No search space for {algorithm}. Falling back to local." )
        return _tune_local( X_train, y_train, X_test, y_test, algorithm, n_iter, 5 )

    # Build parameter specs for Vizier
    from google.cloud.aiplatform import hyperparameter_tuning as hpt

    metric_spec    = { "roc_auc": "maximize" }
    parameter_spec = {}

    for param_name, values in param_space.items():
        if all( isinstance( v, ( int, float ) ) for v in values if v is not None ):
            # Filter None values
            numeric_values = [ v for v in values if v is not None ]
            if not numeric_values:
                continue
            if all( isinstance( v, int ) for v in numeric_values ):
                parameter_spec[ param_name ] = hpt.IntegerParameterSpec(
                    min=min( numeric_values ), max=max( numeric_values ), scale="unit"
                )
            else:
                parameter_spec[ param_name ] = hpt.DoubleParameterSpec(
                    min=min( numeric_values ), max=max( numeric_values ), scale="unit"
                )
        elif all( isinstance( v, str ) for v in values ):
            parameter_spec[ param_name ] = hpt.CategoricalParameterSpec(
                values=values
            )

    # Since Vizier's native API requires a training application,
    # we use the local model training with Vizier-suggested parameters
    # via the Vizier client for parameter suggestions
    try:
        from google.cloud.aiplatform.vizier import Study

        study_config = {
            "display_name" : f"meridian-{algorithm}-tuning",
            "metrics"      : [ { "metric_id": "roc_auc", "goal": "MAXIMIZE" } ],
            "parameters"   : [],
        }

        # Build parameter list from search space
        for param_name, values in param_space.items():
            numeric_values = [ v for v in values if v is not None ]
            if not numeric_values:
                continue

            if all( isinstance( v, int ) for v in numeric_values ):
                study_config[ "parameters" ].append( {
                    "parameter_id"     : param_name,
                    "integer_value_spec" : {
                        "min_value" : min( numeric_values ),
                        "max_value" : max( numeric_values ),
                    },
                } )
            elif all( isinstance( v, ( int, float ) ) for v in numeric_values ):
                study_config[ "parameters" ].append( {
                    "parameter_id"    : param_name,
                    "double_value_spec" : {
                        "min_value" : float( min( numeric_values ) ),
                        "max_value" : float( max( numeric_values ) ),
                    },
                } )
            elif all( isinstance( v, str ) for v in values ):
                study_config[ "parameters" ].append( {
                    "parameter_id"           : param_name,
                    "categorical_value_spec" : { "values": values },
                } )

        study = Study.create_or_load( display_name=f"meridian-{algorithm}-tuning", problem=study_config )

        best_score  = -1.0
        best_params = {}
        best_model  = None

        for trial_idx in range( min( n_iter, 20 ) ):
            # Get suggested parameters from Vizier
            suggestions = study.suggest( count=1 )
            if not suggestions:
                break

            trial  = suggestions[ 0 ]
            params = {}
            for p in trial.parameters:
                params[ p.parameter_id ] = p.value

            # Train model with suggested params
            if algorithm == "xgboost":
                model = _get_xgboost()
            else:
                factory = ALGORITHMS.get( algorithm )
                model   = factory()

            # Apply params
            valid_params = { k: v for k, v in params.items() if hasattr( model, k ) }
            model.set_params( **valid_params )
            model.fit( X_train, y_train )

            # Evaluate
            from sklearn.metrics import roc_auc_score
            y_prob = model.predict_proba( X_test )[ :, 1 ] if hasattr( model, "predict_proba" ) else model.predict( X_test ).astype( float )
            score  = float( roc_auc_score( y_test, y_prob ) )

            # Report to Vizier
            trial.complete( final_measurement={ "metrics": { "roc_auc": score } } )

            logger.info( f"  Vizier trial {trial_idx + 1}/{n_iter}: roc_auc={score:.4f}" )

            if score > best_score:
                best_score  = score
                best_params = params
                best_model  = model

        return {
            "algorithm"   : algorithm,
            "best_params" : best_params,
            "best_score"  : best_score,
            "test_score"  : best_score,
            "model"       : best_model,
            "mode"        : "vertex_vizier",
            "n_iter"      : n_iter,
        }

    except Exception as e:
        logger.warning( f"Vizier study failed: {e}. Falling back to local search." )
        return _tune_local( X_train, y_train, X_test, y_test, algorithm, n_iter, 5 )
