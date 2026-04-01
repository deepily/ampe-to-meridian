"""
Chaos test: Endpoint failure and cache fallback verification.

Simulates prediction endpoint failure and verifies that the
fallback system degrades gracefully through all 3 tiers.

Demonstrates Failure & Recovery Testing and Graceful Degradation competencies.
"""

import os
import shutil
import tempfile

import numpy as np
import pandas as pd
import pytest


class TestEndpointFailure:
    """Simulate endpoint unavailability and verify fallback behavior."""

    def test_model_crash_falls_to_cache( self ):
        """When model raises exception, cached predictions should be served."""
        from serving.cache import PredictionCache
        from serving.fallback import FallbackPredictor

        cache = PredictionCache()

        # Pre-populate cache
        cache.set( "student_001", {
            "student_id"           : "student_001",
            "predicted_class"      : 1,
            "retention_probability": 0.87,
            "model_version"        : "v1",
        } )

        # Create a model that always crashes
        class CrashingModel:
            def predict( self, X ):
                raise RuntimeError( "Model inference crashed!" )
            def predict_proba( self, X ):
                raise RuntimeError( "Model inference crashed!" )

        predictor = FallbackPredictor( cache=cache, model=CrashingModel() )
        result    = predictor.predict( "student_001", features={"hs_gpa": 3.5} )

        assert result[ "served_from" ] == "cache"
        assert result[ "predicted_class" ] == 1

    def test_model_and_cache_down_falls_to_batch( self ):
        """When model crashes and cache is empty, batch predictions used."""
        from serving.cache import PredictionCache
        from serving.fallback import FallbackPredictor

        # Create batch predictions file
        tmpdir = tempfile.mkdtemp()
        try:
            batch_df = pd.DataFrame( {
                "student_id"           : ["s1", "s2", "s3"],
                "predicted_class"      : [1, 0, 1],
                "predicted_probability": [0.85, 0.32, 0.91],
                "model_version"        : ["batch_v1"] * 3,
            } )
            batch_path = os.path.join( tmpdir, "batch_predictions.parquet" )
            batch_df.to_parquet( batch_path, index=False )

            class CrashingModel:
                def predict( self, X ):
                    raise RuntimeError( "Down!" )

            cache     = PredictionCache()  # Empty cache
            predictor = FallbackPredictor(
                cache=cache, model=CrashingModel(),
                batch_predictions_path=batch_path,
            )

            result = predictor.predict( "s2", features={"hs_gpa": 2.5} )

            assert result[ "served_from" ] == "batch"
            assert result[ "predicted_class" ] == 0
            assert result[ "degraded" ] is True
        finally:
            shutil.rmtree( tmpdir )

    def test_total_failure_returns_safe_default( self ):
        """When all tiers fail, return safe default prediction."""
        from serving.cache import PredictionCache
        from serving.fallback import FallbackPredictor

        cache     = PredictionCache()  # Empty
        predictor = FallbackPredictor( cache=cache, model=None )  # No model, no batch

        result = predictor.predict( "unknown_student" )

        assert result[ "served_from" ] == "default"
        assert result[ "degraded" ] is True
        assert result[ "predicted_class" ] == -1
        assert result[ "retention_probability" ] == 0.5  # Safe default

    def test_degradation_tracking_across_requests( self ):
        """FallbackPredictor should track which tier served each request."""
        from serving.cache import PredictionCache
        from serving.fallback import FallbackPredictor

        cache = PredictionCache()
        cache.set( "cached_1", { "student_id": "cached_1", "predicted_class": 1, "retention_probability": 0.9, "model_version": "v1" } )
        cache.set( "cached_2", { "student_id": "cached_2", "predicted_class": 0, "retention_probability": 0.3, "model_version": "v1" } )

        predictor = FallbackPredictor( cache=cache, model=None )

        predictor.predict( "cached_1" )   # cache hit
        predictor.predict( "cached_2" )   # cache hit
        predictor.predict( "unknown_1" )  # default
        predictor.predict( "unknown_2" )  # default

        stats = predictor.stats()
        assert stats[ "tier_counts" ][ "cache" ] == 2
        assert stats[ "tier_counts" ][ "default" ] == 2
        assert stats[ "degraded_pct" ] == 1.0  # All degraded (no live model)

    def test_cache_survives_redis_unavailable( self ):
        """Cache should fall back to local dict when Redis is unreachable."""
        from serving.cache import PredictionCache

        # Try connecting to non-existent Redis
        cache = PredictionCache( redis_host="192.0.2.1", redis_port=6379 )

        # Should still work with local fallback
        cache.set( "test_student", { "predicted_class": 1 } )
        result = cache.get( "test_student" )

        assert result is not None
        assert result[ "predicted_class" ] == 1
        assert cache.stats()[ "mode" ] == "local"

    def test_recovery_after_model_restored( self ):
        """After model comes back, live predictions should resume."""
        from serving.cache import PredictionCache
        from serving.fallback import FallbackPredictor
        from sklearn.dummy import DummyClassifier

        cache = PredictionCache()

        # Phase 1: No model — defaults
        predictor = FallbackPredictor( cache=cache, model=None )
        result1   = predictor.predict( "s1" )
        assert result1[ "served_from" ] == "default"

        # Phase 2: Model restored (needs both classes to have predict_proba work)
        model = DummyClassifier( strategy="most_frequent" )
        model.fit( [[0], [1], [2]], [1, 0, 1] )  # Fit with both classes

        predictor.model = model
        result2 = predictor.predict( "s1", features={"f1": 0} )

        # Should be back to live
        assert result2[ "served_from" ] == "live"
        assert result2[ "degraded" ] is False
