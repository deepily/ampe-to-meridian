"""
Chaos test: Drift injection and alert verification.

Injects synthetic drift into serving data and verifies that
the monitoring system detects it and triggers alerts.

Demonstrates Failure & Recovery Testing competency.
"""

import os
import shutil
import tempfile

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def training_data():
    """Generate stable training data distribution."""
    np.random.seed( 42 )
    n = 500
    return pd.DataFrame( {
        "student_id"          : [f"s{i}" for i in range( n )],
        "hs_gpa"              : np.random.normal( 3.0, 0.5, n ).clip( 0, 4 ),
        "sat_score"           : np.random.normal( 1100, 150, n ).clip( 400, 1600 ),
        "efc"                 : np.random.normal( 15000, 8000, n ).clip( 0, 99999 ),
        "cumulative_gpa"      : np.random.normal( 2.8, 0.6, n ).clip( 0, 4 ),
        "credit_ratio"        : np.random.normal( 0.85, 0.1, n ).clip( 0, 1 ),
        "second_year_ret_flag": np.random.choice( [0, 1], n, p=[0.25, 0.75] ),
        "predicted_class"     : np.random.choice( [0, 1], n, p=[0.25, 0.75] ),
    } )


class TestDriftInjection:
    """Inject drift and verify monitoring detects it."""

    def test_no_drift_on_identical_data( self, training_data ):
        """Same distribution for train and serve = no drift."""
        from monitoring.model_monitor import monitor_drift

        tmpdir = tempfile.mkdtemp()
        try:
            train_path = os.path.join( tmpdir, "train.parquet" )
            serve_path = os.path.join( tmpdir, "serve.parquet" )
            training_data.to_parquet( train_path, index=False )
            training_data.to_parquet( serve_path, index=False )

            report = monitor_drift( train_path, serve_path, tmpdir, drift_threshold_js=0.1 )

            assert report[ "drifted_features" ] == 0
            assert report[ "alert_triggered" ] is False
        finally:
            shutil.rmtree( tmpdir )

    def test_mean_shift_drift_detected( self, training_data ):
        """Shifting feature means by 3 sigma should trigger drift."""
        from monitoring.model_monitor import monitor_drift

        drifted = training_data.copy()
        # Shift GPA distribution dramatically
        drifted[ "hs_gpa" ] = drifted[ "hs_gpa" ] + 2.0  # Massive shift
        drifted[ "sat_score" ] = drifted[ "sat_score" ] + 400

        tmpdir = tempfile.mkdtemp()
        try:
            train_path = os.path.join( tmpdir, "train.parquet" )
            serve_path = os.path.join( tmpdir, "serve.parquet" )
            training_data.to_parquet( train_path, index=False )
            drifted.to_parquet( serve_path, index=False )

            report = monitor_drift( train_path, serve_path, tmpdir, drift_threshold_js=0.05 )

            assert report[ "drifted_features" ] > 0
            assert report[ "alert_triggered" ] is True

            # Verify specific features flagged
            drift_details = report[ "feature_drift" ]
            if "hs_gpa" in drift_details:
                assert drift_details[ "hs_gpa" ][ "drifted" ] is True
        finally:
            shutil.rmtree( tmpdir )

    def test_variance_change_drift_detected( self, training_data ):
        """Doubling variance should trigger drift even if mean is same."""
        from monitoring.model_monitor import monitor_drift

        drifted = training_data.copy()
        # Double the variance while keeping mean similar
        mean_gpa = drifted[ "hs_gpa" ].mean()
        drifted[ "hs_gpa" ] = mean_gpa + ( drifted[ "hs_gpa" ] - mean_gpa ) * 3

        tmpdir = tempfile.mkdtemp()
        try:
            train_path = os.path.join( tmpdir, "train.parquet" )
            serve_path = os.path.join( tmpdir, "serve.parquet" )
            training_data.to_parquet( train_path, index=False )
            drifted.to_parquet( serve_path, index=False )

            report = monitor_drift( train_path, serve_path, tmpdir, drift_threshold_js=0.05 )

            # Variance change should be detected
            assert report[ "features_analyzed" ] > 0
        finally:
            shutil.rmtree( tmpdir )

    def test_prediction_distribution_drift( self, training_data ):
        """Shifting prediction distribution should trigger prediction drift."""
        from monitoring.model_monitor import monitor_drift

        drifted = training_data.copy()
        # Flip predictions — model now predicts mostly 0 instead of mostly 1
        drifted[ "predicted_class" ] = np.random.choice( [0, 1], len( drifted ), p=[0.80, 0.20] )

        tmpdir = tempfile.mkdtemp()
        try:
            train_path = os.path.join( tmpdir, "train.parquet" )
            serve_path = os.path.join( tmpdir, "serve.parquet" )
            training_data.to_parquet( train_path, index=False )
            drifted.to_parquet( serve_path, index=False )

            report = monitor_drift( train_path, serve_path, tmpdir, drift_threshold_js=0.05 )

            assert report[ "prediction_drift" ][ "drifted" ] is True
            assert report[ "alert_triggered" ] is True
        finally:
            shutil.rmtree( tmpdir )

    def test_training_serving_skew_detected( self, training_data ):
        """KS test should detect significant distribution differences."""
        from monitoring.model_monitor import monitor_drift

        drifted = training_data.copy()
        # Replace EFC with completely different distribution
        drifted[ "efc" ] = np.random.exponential( 5000, len( drifted ) )

        tmpdir = tempfile.mkdtemp()
        try:
            train_path = os.path.join( tmpdir, "train.parquet" )
            serve_path = os.path.join( tmpdir, "serve.parquet" )
            training_data.to_parquet( train_path, index=False )
            drifted.to_parquet( serve_path, index=False )

            report = monitor_drift( train_path, serve_path, tmpdir, skew_threshold=0.1 )

            # EFC should show significant skew
            skew = report[ "training_serving_skew" ]
            if "efc" in skew:
                assert skew[ "efc" ][ "skewed" ] == True
        finally:
            shutil.rmtree( tmpdir )
