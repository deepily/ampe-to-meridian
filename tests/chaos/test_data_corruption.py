"""
Chaos test: Data corruption detection.

Verifies that the validate component catches corrupted data
and blocks the pipeline when anomaly thresholds are exceeded.

Demonstrates Failure & Recovery Testing competency.
"""

import os
import shutil
import tempfile

import numpy as np
import pandas as pd
import pytest


class TestDataCorruption:
    """Inject corrupted data and verify TFDV catches it."""

    def test_validate_catches_all_null_column( self ):
        """A column that is entirely null should be flagged."""
        from pipeline.components.validate import validate_data

        df = pd.DataFrame( {
            "student_id"          : ["s1", "s2", "s3"],
            "hs_gpa"              : [None, None, None],
            "sat_score"           : [1200, 1300, 1100],
            "second_year_ret_flag": [1, 0, 1],
        } )

        tmpdir = tempfile.mkdtemp()
        try:
            input_path  = os.path.join( tmpdir, "corrupted.parquet" )
            output_path = os.path.join( tmpdir, "validated.parquet" )
            df.to_parquet( input_path, index=False )

            report = validate_data( input_path, output_path, anomaly_threshold=0 )

            # Should detect 100% null in hs_gpa
            gpa_anomalies = [a for a in report[ "anomalies" ] if a[ "column" ] == "hs_gpa"]
            assert len( gpa_anomalies ) > 0
            assert any( a[ "severity" ] == "ERROR" for a in gpa_anomalies )
        finally:
            shutil.rmtree( tmpdir )

    def test_validate_catches_extreme_outliers( self ):
        """Extreme outlier values should be flagged as out-of-range."""
        from pipeline.components.validate import validate_data

        df = pd.DataFrame( {
            "student_id"          : [f"s{i}" for i in range( 100 )],
            "hs_gpa"              : np.random.normal( 3.0, 0.5, 100 ).clip( 0, 4 ),
            "sat_score"           : [99999] * 10 + list( np.random.randint( 900, 1400, 90 ) ),
            "second_year_ret_flag": np.random.choice( [0, 1], 100 ),
        } )

        tmpdir = tempfile.mkdtemp()
        try:
            input_path  = os.path.join( tmpdir, "outliers.parquet" )
            output_path = os.path.join( tmpdir, "validated.parquet" )
            df.to_parquet( input_path, index=False )

            report = validate_data( input_path, output_path, anomaly_threshold=0 )

            sat_anomalies = [a for a in report[ "anomalies" ] if a[ "column" ] == "sat_score"]
            assert len( sat_anomalies ) > 0
            assert sat_anomalies[ 0 ][ "type" ] == "out_of_range"
        finally:
            shutil.rmtree( tmpdir )

    def test_validate_blocks_on_threshold( self ):
        """Pipeline should raise ValueError when errors exceed threshold."""
        from pipeline.components.validate import validate_data

        df = pd.DataFrame( {
            "student_id"          : [f"s{i}" for i in range( 50 )],
            "hs_gpa"              : [None] * 50,  # 100% null
            "sat_score"           : [99999] * 50,  # 100% out of range
            "second_year_ret_flag": [1] * 50,
        } )

        tmpdir = tempfile.mkdtemp()
        try:
            input_path  = os.path.join( tmpdir, "bad_data.parquet" )
            output_path = os.path.join( tmpdir, "validated.parquet" )
            df.to_parquet( input_path, index=False )

            with pytest.raises( ValueError, match="Data validation failed" ):
                validate_data( input_path, output_path, anomaly_threshold=1 )
        finally:
            shutil.rmtree( tmpdir )

    def test_validate_passes_clean_data( self ):
        """Clean data should pass validation without errors."""
        from pipeline.components.validate import validate_data

        df = pd.DataFrame( {
            "student_id"          : [f"s{i}" for i in range( 100 )],
            "hs_gpa"              : np.random.normal( 3.0, 0.5, 100 ).clip( 0.5, 4.0 ),
            "sat_score"           : np.random.randint( 800, 1400, 100 ),
            "second_year_ret_flag": np.random.choice( [0, 1], 100 ),
        } )

        tmpdir = tempfile.mkdtemp()
        try:
            input_path  = os.path.join( tmpdir, "clean.parquet" )
            output_path = os.path.join( tmpdir, "validated.parquet" )
            df.to_parquet( input_path, index=False )

            report = validate_data( input_path, output_path, anomaly_threshold=0 )
            assert report[ "error_count" ] == 0
        finally:
            shutil.rmtree( tmpdir )
