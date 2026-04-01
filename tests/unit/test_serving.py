"""
Unit tests for Phase 4: Serving, Cache, Fallback, Monitoring, Deploy.
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
def full_pipeline_output( synth_data_dir ):
    """Run Phases 2-3 pipeline to generate input for Phase 4."""
    from pipeline.vertex_pipeline import run_local
    from pipeline.components.train import train
    from pipeline.components.tune import tune
    from pipeline.components.evaluate import evaluate
    from pipeline.components.explain import explain
    from pipeline.components.register import register
    from pipeline.components.deploy import deploy

    output_dir = tempfile.mkdtemp( prefix="meridian_p4_" )

    # Phase 2: Pipeline
    run_local( synth_data_dir, output_dir )

    # Phase 3: Train + Tune + Evaluate + Explain + Register
    reduced_path = os.path.join( output_dir, "08_reduced.parquet" )
    training_dir = os.path.join( output_dir, "training" )
    train( reduced_path, training_dir, algorithms=["random_forest"], smote_strategies=["none"], test_size=0.3 )
    tune( reduced_path, training_dir, algorithm="random_forest", n_iter=3, cv_folds=3, test_size=0.3 )

    eval_dir = os.path.join( output_dir, "evaluation" )
    eval_report = evaluate( reduced_path, training_dir, eval_dir )

    explain_dir = os.path.join( output_dir, "explanation" )
    pkl_files   = [f for f in os.listdir( training_dir ) if f.endswith( ".pkl" )]
    model_path  = os.path.join( training_dir, pkl_files[ 0 ] )
    expl_report = explain( reduced_path, model_path, explain_dir )

    reg_dir = os.path.join( output_dir, "registry" )
    register( model_path, eval_report, expl_report, reg_dir )

    # Phase 4: Deploy (batch predictions)
    deploy_dir = os.path.join( output_dir, "deployment" )
    deploy( model_path, reduced_path, deploy_dir )

    yield { "dir": output_dir, "model_path": model_path, "reduced_path": reduced_path, "deploy_dir": deploy_dir }
    shutil.rmtree( output_dir, ignore_errors=True )


@pytest.fixture( scope="module" )
def synth_data_dir( small_dataset ):
    d = tempfile.mkdtemp( prefix="meridian_p4_synth_" )
    for name, df in small_dataset.items():
        df.to_parquet( os.path.join( d, f"{name}.parquet" ), index=False )
    yield d
    shutil.rmtree( d, ignore_errors=True )


# ==================== Deploy ====================

class TestDeploy:

    def test_deploy_produces_predictions( self, full_pipeline_output ):
        pred_path = os.path.join( full_pipeline_output[ "deploy_dir" ], "predictions.parquet" )
        assert os.path.exists( pred_path )

        df = pd.read_parquet( pred_path )
        assert len( df ) > 0
        assert "predicted_class" in df.columns
        assert "predicted_probability" in df.columns
        assert set( df[ "predicted_class" ].unique() ).issubset( {0, 1} )

    def test_deploy_report_has_accuracy( self, full_pipeline_output ):
        report_path = os.path.join( full_pipeline_output[ "deploy_dir" ], "deployment_report.json" )
        with open( report_path ) as f:
            report = json.load( f )

        assert report[ "total_predictions" ] > 0
        assert "batch_accuracy" in report
        assert report[ "batch_accuracy" ] > 0.4

    def test_predictions_probabilities_valid( self, full_pipeline_output ):
        pred_path = os.path.join( full_pipeline_output[ "deploy_dir" ], "predictions.parquet" )
        df = pd.read_parquet( pred_path )

        assert ( df[ "predicted_probability" ] >= 0 ).all()
        assert ( df[ "predicted_probability" ] <= 1 ).all()


# ==================== Cache ====================

class TestCache:

    def test_cache_set_and_get( self ):
        from serving.cache import PredictionCache
        cache = PredictionCache()

        cache.set( "student_123", { "predicted_class": 1, "probability": 0.85 } )
        result = cache.get( "student_123" )

        assert result is not None
        assert result[ "predicted_class" ] == 1

    def test_cache_miss_returns_none( self ):
        from serving.cache import PredictionCache
        cache = PredictionCache()

        result = cache.get( "nonexistent_student" )
        assert result is None

    def test_cache_stats( self ):
        from serving.cache import PredictionCache
        cache = PredictionCache()

        cache.set( "s1", { "p": 1 } )
        cache.get( "s1" )  # hit
        cache.get( "s2" )  # miss

        stats = cache.stats()
        assert stats[ "hits" ] == 1
        assert stats[ "misses" ] == 1
        assert stats[ "mode" ] == "local"


# ==================== Fallback ====================

class TestFallback:

    def test_fallback_tier1_live( self, full_pipeline_output ):
        from serving.cache import PredictionCache
        from serving.fallback import FallbackPredictor

        model_path = full_pipeline_output[ "model_path" ]
        with open( model_path, "rb" ) as f:
            model = pickle.load( f )

        cache     = PredictionCache()
        predictor = FallbackPredictor( cache=cache, model=model )

        # Need to provide features matching model input
        reduced = pd.read_parquet( full_pipeline_output[ "reduced_path" ] )
        row     = reduced.drop( columns=["second_year_ret_flag", "student_id"], errors="ignore" ).iloc[ 0 ]

        result = predictor.predict( "test_student", features=row.to_dict() )

        assert result[ "served_from" ] == "live"
        assert result[ "degraded" ] is False
        assert result[ "predicted_class" ] in [0, 1]

    def test_fallback_tier2_cache( self ):
        from serving.cache import PredictionCache
        from serving.fallback import FallbackPredictor

        cache = PredictionCache()
        cache.set( "cached_student", {
            "student_id": "cached_student",
            "predicted_class": 1,
            "retention_probability": 0.9,
            "model_version": "v1",
        } )

        # No model — forces cache tier
        predictor = FallbackPredictor( cache=cache, model=None )
        result    = predictor.predict( "cached_student" )

        assert result[ "served_from" ] == "cache"
        assert result[ "predicted_class" ] == 1

    def test_fallback_tier3_batch( self, full_pipeline_output ):
        from serving.cache import PredictionCache
        from serving.fallback import FallbackPredictor

        pred_path = os.path.join( full_pipeline_output[ "deploy_dir" ], "predictions.parquet" )
        cache     = PredictionCache()

        # No model, empty cache — should fall back to batch
        predictor = FallbackPredictor( cache=cache, model=None, batch_predictions_path=pred_path )

        # Get a student_id from predictions
        pred_df    = pd.read_parquet( pred_path )
        student_id = str( pred_df[ "student_id" ].iloc[ 0 ] )

        result = predictor.predict( student_id )
        assert result[ "served_from" ] == "batch"
        assert result[ "degraded" ] is True

    def test_fallback_tier4_default( self ):
        from serving.cache import PredictionCache
        from serving.fallback import FallbackPredictor

        cache     = PredictionCache()
        predictor = FallbackPredictor( cache=cache, model=None )

        result = predictor.predict( "unknown_student" )
        assert result[ "served_from" ] == "default"
        assert result[ "degraded" ] is True
        assert result[ "predicted_class" ] == -1

    def test_fallback_stats( self, full_pipeline_output ):
        from serving.cache import PredictionCache
        from serving.fallback import FallbackPredictor

        cache     = PredictionCache()
        predictor = FallbackPredictor( cache=cache, model=None )

        predictor.predict( "a" )
        predictor.predict( "b" )

        stats = predictor.stats()
        assert stats[ "total_requests" ] == 2
        assert stats[ "degraded_pct" ] == 1.0  # All degraded (no model)


# ==================== Model Monitoring ====================

class TestModelMonitor:

    def test_drift_detection_no_drift( self, full_pipeline_output ):
        """Same data for train and serve should show minimal drift."""
        from monitoring.model_monitor import monitor_drift

        reduced_path = full_pipeline_output[ "reduced_path" ]
        monitor_dir  = os.path.join( full_pipeline_output[ "dir" ], "monitoring" )

        # Use same data for both — should show ~zero drift
        report = monitor_drift(
            training_data_path=reduced_path,
            serving_data_path=reduced_path,
            output_dir=monitor_dir,
            drift_threshold_js=0.1,
        )

        assert report[ "drifted_features" ] == 0
        assert report[ "alert_triggered" ] is False

    def test_drift_detection_with_synthetic_drift( self, full_pipeline_output ):
        """Artificially shifted data should trigger drift alerts."""
        from monitoring.model_monitor import monitor_drift

        reduced_path = full_pipeline_output[ "reduced_path" ]
        monitor_dir  = os.path.join( full_pipeline_output[ "dir" ], "monitoring_drift" )

        # Create drifted version
        df = pd.read_parquet( reduced_path )
        drifted = df.copy()
        numeric_cols = drifted.select_dtypes( include=[np.number] ).columns.tolist()
        for col in numeric_cols[ :5 ]:
            drifted[ col ] = drifted[ col ] + drifted[ col ].std() * 3  # Shift by 3 sigma

        drifted_path = os.path.join( full_pipeline_output[ "dir" ], "drifted_data.parquet" )
        drifted.to_parquet( drifted_path, index=False )

        report = monitor_drift(
            training_data_path=reduced_path,
            serving_data_path=drifted_path,
            output_dir=monitor_dir,
            drift_threshold_js=0.05,
        )

        assert report[ "drifted_features" ] > 0
        assert report[ "alert_triggered" ] is True

    def test_drift_report_saved( self, full_pipeline_output ):
        monitor_dir = os.path.join( full_pipeline_output[ "dir" ], "monitoring" )
        report_path = os.path.join( monitor_dir, "drift_report.json" )

        if not os.path.exists( report_path ):
            pytest.skip( "Requires monitor output" )

        with open( report_path ) as f:
            report = json.load( f )

        assert "feature_drift" in report
        assert "prediction_drift" in report


# ==================== FastAPI Predictor ====================

class TestPredictorAPI:

    def test_health_endpoint( self ):
        from fastapi.testclient import TestClient
        from serving.predictor import app

        client   = TestClient( app )
        response = client.get( "/health" )

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "model_loaded" in data

    def test_openapi_spec_exists( self ):
        from fastapi.testclient import TestClient
        from serving.predictor import app

        client   = TestClient( app )
        response = client.get( "/api/v1/openapi.json" )

        assert response.status_code == 200
        spec = response.json()
        assert spec[ "info" ][ "title" ] == "Meridian Retention Prediction API"
        assert "/api/v1/predict" in spec[ "paths" ]
