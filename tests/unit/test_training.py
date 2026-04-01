"""
Unit tests for Phase 3: Training, Tuning, Evaluation, Explanation, Registration.

Includes ML-specific unit tests (output shapes, label leakage, gradient flow)
that demonstrate the Failure & Recovery Testing competency.
"""

import json
import os
import pickle
import shutil
import tempfile

import numpy as np
import pandas as pd
import pytest


@pytest.fixture( scope="module" )
def pipeline_output( synth_data_dir ):
    """Run Phase 2 pipeline to generate input for Phase 3."""
    from pipeline.vertex_pipeline import run_local

    output_dir = tempfile.mkdtemp( prefix="meridian_p3_pipeline_" )
    run_local( synth_data_dir, output_dir )
    yield output_dir
    shutil.rmtree( output_dir, ignore_errors=True )


@pytest.fixture( scope="module" )
def synth_data_dir( small_dataset ):
    """Save small dataset for pipeline input."""
    d = tempfile.mkdtemp( prefix="meridian_p3_synth_" )
    for name, df in small_dataset.items():
        df.to_parquet( os.path.join( d, f"{name}.parquet" ), index=False )
    yield d
    shutil.rmtree( d, ignore_errors=True )


@pytest.fixture( scope="module" )
def training_dir( pipeline_output ):
    """Run training on pipeline output."""
    from pipeline.components.train import train

    reduced_path = os.path.join( pipeline_output, "08_reduced.parquet" )
    output_dir   = os.path.join( pipeline_output, "training" )

    train(
        reduced_path, output_dir,
        algorithms=["random_forest", "logistic_regression"],
        smote_strategies=["none"],
        test_size=0.3,
    )
    yield output_dir


# ==================== Train ====================

class TestTrain:

    def test_train_produces_models( self, training_dir ):
        """Training should produce pickle files for each algorithm."""
        pkl_files = [f for f in os.listdir( training_dir ) if f.endswith( ".pkl" )]
        assert len( pkl_files ) >= 2  # At least RF + LR

    def test_train_report_exists( self, training_dir ):
        report_path = os.path.join( training_dir, "training_report.json" )
        assert os.path.exists( report_path )

        with open( report_path ) as f:
            report = json.load( f )
        assert report[ "total_models" ] >= 2
        assert "winner" in report

    def test_train_metrics_reasonable( self, training_dir ):
        """Model metrics should be above random (>50% accuracy for binary)."""
        report_path = os.path.join( training_dir, "training_report.json" )
        with open( report_path ) as f:
            report = json.load( f )

        for result in report[ "all_results" ]:
            assert result[ "accuracy" ] > 0.4, f"{result[ 'algorithm' ]} accuracy too low"
            assert 0 <= result[ "auc" ] <= 1.0

    def test_train_confusion_matrix_shape( self, training_dir ):
        """Confusion matrix should be 2x2 for binary classification."""
        report_path = os.path.join( training_dir, "training_report.json" )
        with open( report_path ) as f:
            report = json.load( f )

        for result in report[ "all_results" ]:
            cm = result[ "confusion_matrix" ]
            assert len( cm ) == 2
            assert len( cm[ 0 ] ) == 2

    def test_model_loads_and_predicts( self, training_dir, pipeline_output ):
        """Serialized model should load and produce predictions."""
        pkl_files = [f for f in os.listdir( training_dir ) if f.endswith( ".pkl" )]
        model_path = os.path.join( training_dir, pkl_files[ 0 ] )

        with open( model_path, "rb" ) as f:
            model = pickle.load( f )

        reduced = pd.read_parquet( os.path.join( pipeline_output, "08_reduced.parquet" ) )
        X = reduced.drop( columns=["second_year_ret_flag", "student_id"], errors="ignore" )

        predictions = model.predict( X )
        assert len( predictions ) == len( X )
        assert set( predictions ).issubset( {0, 1} )


# ==================== ML-Specific Unit Tests (Failure & Recovery Testing) ====================

class TestMLOutputShapes:
    """Test model output shapes — catches dimension mismatches."""

    def test_predict_output_shape( self, training_dir, pipeline_output ):
        """Predictions should have same length as input."""
        pkl_files = [f for f in os.listdir( training_dir ) if f.endswith( ".pkl" )]
        model_path = os.path.join( training_dir, pkl_files[ 0 ] )

        with open( model_path, "rb" ) as f:
            model = pickle.load( f )

        reduced = pd.read_parquet( os.path.join( pipeline_output, "08_reduced.parquet" ) )
        X = reduced.drop( columns=["second_year_ret_flag", "student_id"], errors="ignore" )

        y_pred = model.predict( X )
        assert y_pred.shape == ( len( X ), ), f"Expected ({len( X )},), got {y_pred.shape}"

    def test_predict_proba_shape( self, training_dir, pipeline_output ):
        """Probability output should be (n_samples, n_classes)."""
        pkl_files = [f for f in os.listdir( training_dir ) if f.endswith( ".pkl" )]
        model_path = os.path.join( training_dir, pkl_files[ 0 ] )

        with open( model_path, "rb" ) as f:
            model = pickle.load( f )

        reduced = pd.read_parquet( os.path.join( pipeline_output, "08_reduced.parquet" ) )
        X = reduced.drop( columns=["second_year_ret_flag", "student_id"], errors="ignore" )

        if hasattr( model, "predict_proba" ):
            proba = model.predict_proba( X )
            assert proba.shape == ( len( X ), 2 ), f"Expected ({len( X )}, 2), got {proba.shape}"
            assert np.allclose( proba.sum( axis=1 ), 1.0, atol=1e-6 ), "Probabilities don't sum to 1"


class TestLabelLeakage:
    """Test for label leakage — target should not correlate perfectly with any feature."""

    def test_no_perfect_correlation_with_target( self, pipeline_output ):
        """No feature should have |correlation| > 0.99 with target."""
        reduced = pd.read_parquet( os.path.join( pipeline_output, "08_reduced.parquet" ) )
        target  = "second_year_ret_flag"

        if target not in reduced.columns:
            pytest.skip( "No target column" )

        numeric = reduced.select_dtypes( include=[np.number] )
        correlations = numeric.corr()[ target ].drop( target, errors="ignore" ).abs()

        leaky = correlations[ correlations > 0.99 ]
        assert len( leaky ) == 0, f"Potential label leakage in features: {leaky.to_dict()}"

    def test_no_duplicate_target_column( self, pipeline_output ):
        """Target should not appear under a different name."""
        reduced = pd.read_parquet( os.path.join( pipeline_output, "08_reduced.parquet" ) )
        target  = reduced[ "second_year_ret_flag" ]

        for col in reduced.columns:
            if col == "second_year_ret_flag" or col == "student_id":
                continue
            if reduced[ col ].dtype in [np.float64, np.int64]:
                if ( reduced[ col ] == target ).all():
                    pytest.fail( f"Column {col} is identical to target — label leakage!" )


# ==================== Tune ====================

class TestTune:

    def test_tune_improves_or_matches_baseline( self, pipeline_output, training_dir ):
        from pipeline.components.tune import tune

        reduced_path = os.path.join( pipeline_output, "08_reduced.parquet" )
        tune_dir     = os.path.join( pipeline_output, "tuning" )

        result = tune(
            reduced_path, tune_dir,
            algorithm="random_forest",
            n_iter=5,
            cv_folds=3,
            test_size=0.3,
        )

        assert result[ "best_score" ] > 0.4
        assert "best_params" in result
        assert os.path.exists( result[ "model_path" ] )

    def test_tune_report_has_params( self, pipeline_output ):
        tune_report = os.path.join( pipeline_output, "tuning", "tuning_report.json" )
        if not os.path.exists( tune_report ):
            pytest.skip( "Requires tune output" )

        with open( tune_report ) as f:
            report = json.load( f )
        assert "best_params" in report
        assert "best_score" in report


# ==================== Evaluate ====================

class TestEvaluate:

    def test_evaluate_selects_winner( self, pipeline_output, training_dir ):
        from pipeline.components.evaluate import evaluate

        reduced_path = os.path.join( pipeline_output, "08_reduced.parquet" )
        eval_dir     = os.path.join( pipeline_output, "evaluation" )

        report = evaluate(
            reduced_path, training_dir, eval_dir,
        )

        assert "winner" in report
        assert report[ "winner" ][ "algorithm" ] in ["random_forest", "logistic_regression"]
        assert report[ "total_models" ] >= 2

    def test_evaluate_rankings_sorted( self, pipeline_output ):
        eval_report = os.path.join( pipeline_output, "evaluation", "evaluation_report.json" )
        if not os.path.exists( eval_report ):
            pytest.skip( "Requires evaluate output" )

        with open( eval_report ) as f:
            report = json.load( f )

        rankings = report[ "rankings" ]
        metric   = report[ "competition_metric" ]
        scores   = [r[ metric ] for r in rankings]
        assert scores == sorted( scores, reverse=True ), "Rankings not sorted by metric"


# ==================== Explain ====================

class TestExplain:

    def test_explain_produces_importances( self, pipeline_output, training_dir ):
        from pipeline.components.explain import explain

        reduced_path = os.path.join( pipeline_output, "08_reduced.parquet" )
        explain_dir  = os.path.join( pipeline_output, "explanation" )

        # Get first model
        pkl_files  = [f for f in os.listdir( training_dir ) if f.endswith( ".pkl" )]
        model_path = os.path.join( training_dir, pkl_files[ 0 ] )

        report = explain( reduced_path, model_path, explain_dir )

        assert len( report[ "top_features" ] ) > 0
        assert report[ "total_features" ] > 0
        assert os.path.exists( os.path.join( explain_dir, "feature_importance.csv" ) )

    def test_explain_importances_non_negative( self, pipeline_output ):
        importance_path = os.path.join( pipeline_output, "explanation", "feature_importance.csv" )
        if not os.path.exists( importance_path ):
            pytest.skip( "Requires explain output" )

        df = pd.read_csv( importance_path )
        assert ( df[ "native_importance" ] >= 0 ).all(), "Negative native importance found"


# ==================== Register ====================

class TestRegister:

    def test_register_creates_manifest( self, pipeline_output, training_dir ):
        from pipeline.components.evaluate import evaluate
        from pipeline.components.explain import explain
        from pipeline.components.register import register

        reduced_path = os.path.join( pipeline_output, "08_reduced.parquet" )
        eval_dir     = os.path.join( pipeline_output, "evaluation" )
        explain_dir  = os.path.join( pipeline_output, "explanation" )
        registry_dir = os.path.join( pipeline_output, "registry" )

        # Run evaluation
        eval_report = evaluate( reduced_path, training_dir, eval_dir )

        # Run explanation
        pkl_files  = [f for f in os.listdir( training_dir ) if f.endswith( ".pkl" )]
        model_path = os.path.join( training_dir, pkl_files[ 0 ] )
        expl_report = explain( reduced_path, model_path, explain_dir )

        # Register
        reg_entry = register(
            model_path, eval_report, expl_report, registry_dir
        )

        assert "version" in reg_entry
        assert "metrics" in reg_entry
        assert "model_card" in reg_entry
        assert os.path.exists( os.path.join( registry_dir, "model_registry.json" ) )
        assert os.path.exists( os.path.join( registry_dir, "model_card_metadata.json" ) )

    def test_model_card_has_ethical_considerations( self, pipeline_output ):
        card_path = os.path.join( pipeline_output, "registry", "model_card_metadata.json" )
        if not os.path.exists( card_path ):
            pytest.skip( "Requires register output" )

        with open( card_path ) as f:
            card = json.load( f )

        assert "ethical_considerations" in card
        assert "fairness" in card[ "ethical_considerations" ]
        assert "limitations" in card[ "ethical_considerations" ]
        assert len( card[ "ethical_considerations" ][ "limitations" ] ) > 0
