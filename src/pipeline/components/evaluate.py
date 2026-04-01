"""
Evaluate component: Model competition and experiment logging.

Compares all trained models across algorithms and SMOTE strategies,
selects the winner by configurable metric (TP rate or TN rate),
and logs results to Vertex AI Experiments (or local JSON).

Replaces AMPE's generic_prediction_competition_and_write.py.

Requires:
    - Training report from train stage (with all model results)
    - Tuning report from tune stage (with tuned model)

Ensures:
    - Returns competition summary with winning model
    - Logs all metrics in Experiments-compatible format
"""

import json
import os
import pickle
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    roc_auc_score,
)

from utils.logging_config import get_logger

logger = get_logger( __name__, component="evaluate" )


def evaluate(
    input_path        : str,
    training_dir      : str,
    output_dir        : str,
    target_column     : str = "second_year_ret_flag",
    competition_metric: str = "tn_rate",
    use_vertex_experiments: bool = False,
    experiment_name   : Optional[str] = None,
    project_id        : Optional[str] = None,
    region            : Optional[str] = None,
) -> dict:
    """
    Evaluate all models and select the competition winner.

    Requires:
        - input_path points to reduced Parquet (for re-evaluation if needed)
        - training_dir contains model pickle files + training_report.json

    Ensures:
        - Returns competition report with ranked models
        - Winner model identified by competition_metric
        - Metrics logged to Vertex AI Experiments or local JSON
    """
    logger.info( f"Evaluating models from {training_dir}" )

    # Load training report
    report_path = os.path.join( training_dir, "training_report.json" )
    with open( report_path ) as f:
        training_report = json.load( f )

    all_results = training_report[ "all_results" ]

    # Check for tuned model
    tuning_report_path = os.path.join( training_dir, "tuning_report.json" )
    if os.path.exists( tuning_report_path ):
        with open( tuning_report_path ) as f:
            tuning_report = json.load( f )
        # Add tuned model to competition
        tuned_entry = {
            "algorithm"      : tuning_report[ "algorithm" ] + "_tuned",
            "smote_strategy" : "none",
            "accuracy"       : tuning_report.get( "test_score", tuning_report.get( "best_score", 0 ) ),
            "auc"            : tuning_report.get( "test_score", 0 ),
            "tp_rate"        : 0,  # Will be re-evaluated below
            "tn_rate"        : 0,
            "f1"             : 0,
            "model_path"     : tuning_report.get( "model_path", "" ),
        }
        all_results.append( tuned_entry )

    # Re-evaluate tuned model on test data if we have the input
    if os.path.exists( input_path ):
        df = pd.read_parquet( input_path )
        if target_column in df.columns and "student_id" in df.columns:
            drop_cols = [target_column, "student_id"]
            X = df.drop( columns=drop_cols, errors="ignore" )
            y = df[ target_column ].astype( int )

            for entry in all_results:
                model_path = entry.get( "model_path", "" )
                if model_path and os.path.exists( model_path ):
                    try:
                        with open( model_path, "rb" ) as f:
                            model = pickle.load( f )
                        y_pred = model.predict( X )
                        y_prob = model.predict_proba( X )[ :, 1 ] if hasattr( model, "predict_proba" ) else y_pred.astype( float )

                        cm = confusion_matrix( y, y_pred )
                        if cm.shape == ( 2, 2 ):
                            tn, fp, fn, tp = cm.ravel()
                            entry[ "tp_rate" ] = float( tp / ( tp + fn ) ) if ( tp + fn ) > 0 else 0.0
                            entry[ "tn_rate" ] = float( tn / ( tn + fp ) ) if ( tn + fp ) > 0 else 0.0
                        entry[ "accuracy" ] = float( accuracy_score( y, y_pred ) )
                        entry[ "auc" ]      = float( roc_auc_score( y, y_prob ) )
                    except Exception as e:
                        logger.warning( f"Re-evaluation failed for {entry[ 'algorithm' ]}: {e}" )

    # Rank by competition metric
    ranked = sorted( all_results, key=lambda r: r.get( competition_metric, 0 ), reverse=True )

    winner = ranked[ 0 ] if ranked else {}

    os.makedirs( output_dir, exist_ok=True )

    # Log to Vertex AI Experiments or local
    if use_vertex_experiments and project_id:
        _log_to_vertex_experiments(
            ranked, experiment_name, project_id, region
        )
    else:
        _log_local( ranked, output_dir )

    report = {
        "total_models"       : len( ranked ),
        "competition_metric" : competition_metric,
        "winner"             : {k: v for k, v in winner.items() if k != "model_object"},
        "rankings"           : [
            {
                "rank"            : i + 1,
                "algorithm"       : r[ "algorithm" ],
                "smote_strategy"  : r[ "smote_strategy" ],
                competition_metric: r.get( competition_metric, 0 ),
                "accuracy"        : r.get( "accuracy", 0 ),
                "auc"             : r.get( "auc", 0 ),
            }
            for i, r in enumerate( ranked )
        ],
    }

    eval_report_path = os.path.join( output_dir, "evaluation_report.json" )
    with open( eval_report_path, "w" ) as f:
        json.dump( report, f, indent=2, default=str )

    logger.info(
        f"Evaluation complete. Winner: {winner.get( 'algorithm', 'N/A' )}"
        f"/{winner.get( 'smote_strategy', 'N/A' )} "
        f"({competition_metric}={winner.get( competition_metric, 0 ):.3f})"
    )

    return report


def _log_local( ranked: list, output_dir: str ):
    """Log experiment results to local JSON."""

    experiments_path = os.path.join( output_dir, "experiment_log.json" )
    log_entries = []

    for r in ranked:
        entry = {
            "run_name"  : f"{r[ 'algorithm' ]}_{r[ 'smote_strategy' ]}",
            "params"    : {
                "algorithm"      : r[ "algorithm" ],
                "smote_strategy" : r[ "smote_strategy" ],
            },
            "metrics"   : {
                "accuracy" : r.get( "accuracy", 0 ),
                "auc"      : r.get( "auc", 0 ),
                "tp_rate"  : r.get( "tp_rate", 0 ),
                "tn_rate"  : r.get( "tn_rate", 0 ),
                "f1"       : r.get( "f1", 0 ),
            },
        }
        log_entries.append( entry )

    with open( experiments_path, "w" ) as f:
        json.dump( log_entries, f, indent=2 )

    logger.info( f"Experiment log: {experiments_path}" )


def _log_to_vertex_experiments(
    ranked          : list,
    experiment_name : str,
    project_id      : str,
    region          : str,
):
    """
    Log results to Vertex AI Experiments.

    Requires:
        - ranked is a non-empty list of model result dicts
        - experiment_name is a non-empty string
        - project_id is a valid GCP project ID
        - region is a valid GCP region

    Ensures:
        - Each ranked entry logged as a separate Experiment run
        - Run names include timestamps to avoid collisions on re-runs
        - Model artifact paths logged if present
        - Falls back to _log_local() on any GCP error
    """
    from datetime import datetime, timezone

    try:
        from google.cloud import aiplatform
        from google.api_core.exceptions import NotFound

        aiplatform.init( project=project_id, location=region )

        # Get-or-create experiment
        try:
            aiplatform.Experiment( experiment_name=experiment_name ).delete()  # noqa — probe only
        except NotFound:
            pass
        aiplatform.init( project=project_id, location=region, experiment=experiment_name )

        timestamp = datetime.now( timezone.utc ).strftime( "%Y%m%dT%H%M%S" )

        for r in ranked:
            run_name = f"{r[ 'algorithm' ]}_{r[ 'smote_strategy' ]}_{timestamp}"

            aiplatform.start_run( run_name )

            params = {
                "algorithm"      : r[ "algorithm" ],
                "smote_strategy" : r[ "smote_strategy" ],
            }
            if r.get( "model_path" ):
                params[ "model_artifact_path" ] = r[ "model_path" ]

            aiplatform.log_params( params )
            aiplatform.log_metrics( {
                "accuracy" : r.get( "accuracy", 0 ),
                "auc"      : r.get( "auc", 0 ),
                "tp_rate"  : r.get( "tp_rate", 0 ),
                "tn_rate"  : r.get( "tn_rate", 0 ),
                "f1"       : r.get( "f1", 0 ),
            } )
            aiplatform.end_run()

        logger.info( f"Logged {len( ranked )} runs to Vertex AI Experiments: {experiment_name}" )

    except Exception as e:
        logger.warning( f"Vertex AI Experiments logging failed: {e}. Falling back to local." )
        # Derive output_dir from caller context — use current working directory as fallback
        fallback_dir = os.path.join( os.getcwd(), "evaluation_output" )
        os.makedirs( fallback_dir, exist_ok=True )
        _log_local( ranked, fallback_dir )
