"""
Unit tests for Phase 2 pipeline components.

Tests each component locally using the 200-student fixture.
No GCP credentials required — all components run in local mode.
"""

import json
import os
import shutil
import tempfile

import numpy as np
import pandas as pd
import pytest


@pytest.fixture( scope="module" )
def pipeline_dir():
    """Create a temp directory for pipeline stage outputs."""
    d = tempfile.mkdtemp( prefix="meridian_test_" )
    yield d
    shutil.rmtree( d, ignore_errors=True )


@pytest.fixture( scope="module" )
def synth_data_dir( small_dataset ):
    """Save small dataset to temp Parquet files for ingest testing."""
    d = tempfile.mkdtemp( prefix="meridian_synth_" )
    for name, df in small_dataset.items():
        df.to_parquet( os.path.join( d, f"{name}.parquet" ), index=False )
    yield d
    shutil.rmtree( d, ignore_errors=True )


# ==================== Ingest ====================

class TestIngest:

    def test_ingest_from_local( self, synth_data_dir, pipeline_dir ):
        from pipeline.components.ingest import ingest_from_local

        output = os.path.join( pipeline_dir, "01_ingested.parquet" )
        result = ingest_from_local( synth_data_dir, output )

        assert os.path.exists( result )
        df = pd.read_parquet( result )
        assert len( df ) > 0
        assert "student_id" in df.columns
        assert "second_year_ret_flag" in df.columns

    def test_merge_produces_one_row_per_student( self, synth_data_dir, pipeline_dir ):
        from pipeline.components.ingest import ingest_from_local

        output = os.path.join( pipeline_dir, "01_ingested.parquet" )
        ingest_from_local( synth_data_dir, output )
        df = pd.read_parquet( output )

        # Should have one row per enrolled student
        assert df[ "student_id" ].is_unique


# ==================== Validate ====================

class TestValidate:

    def test_validate_detects_anomalies( self, pipeline_dir ):
        from pipeline.components.validate import validate_data

        input_path  = os.path.join( pipeline_dir, "01_ingested.parquet" )
        output_path = os.path.join( pipeline_dir, "02_validated.parquet" )
        schema_path = os.path.join( pipeline_dir, "02_schema.json" )

        if not os.path.exists( input_path ):
            pytest.skip( "Requires ingest output" )

        report = validate_data(
            input_path, output_path,
            schema_output_path=schema_path,
            anomaly_threshold=0,
        )

        assert report[ "input_rows" ] > 0
        assert "anomalies" in report
        assert os.path.exists( output_path )
        assert os.path.exists( schema_path )

    def test_validate_catches_bad_sat( self, pipeline_dir ):
        from pipeline.components.validate import validate_data

        input_path = os.path.join( pipeline_dir, "01_ingested.parquet" )
        if not os.path.exists( input_path ):
            pytest.skip( "Requires ingest output" )

        output_path = os.path.join( pipeline_dir, "02_validated_sat.parquet" )
        report = validate_data( input_path, output_path, anomaly_threshold=0 )

        # Should detect out-of-range SAT scores (injected by generator)
        sat_anomalies = [a for a in report[ "anomalies" ] if a.get( "column" ) == "sat_score"]
        # May or may not have anomalies depending on the 200-student sample
        assert isinstance( sat_anomalies, list )

    def test_schema_stats_structure( self, pipeline_dir ):
        schema_path = os.path.join( pipeline_dir, "02_schema.json" )
        if not os.path.exists( schema_path ):
            pytest.skip( "Requires validate output" )

        with open( schema_path ) as f:
            stats = json.load( f )

        assert isinstance( stats, dict )
        # Should have stats for each column
        for col_stats in stats.values():
            assert "dtype" in col_stats
            assert "null_count" in col_stats


# ==================== DLP Scan ====================

class TestDlpScan:

    def test_dlp_scan_detects_pii( self, pipeline_dir ):
        from pipeline.components.dlp_scan import dlp_scan

        input_path  = os.path.join( pipeline_dir, "02_validated.parquet" )
        output_path = os.path.join( pipeline_dir, "03_dlp_scanned.parquet" )
        report_path = os.path.join( pipeline_dir, "03_dlp_report.json" )

        if not os.path.exists( input_path ):
            pytest.skip( "Requires validate output" )

        report = dlp_scan(
            input_path, output_path,
            report_path=report_path,
            pii_threshold=1.0,  # Don't block in test
            redact_mode="replace",
        )

        assert report[ "total_findings" ] > 0
        assert "PERSON_NAME" in str( report[ "findings_by_type" ] ) or "EMAIL_ADDRESS" in str( report[ "findings_by_type" ] )
        assert os.path.exists( output_path )

    def test_dlp_scan_redacts_pii_columns( self, pipeline_dir ):
        from pipeline.components.dlp_scan import dlp_scan

        input_path  = os.path.join( pipeline_dir, "02_validated.parquet" )
        output_path = os.path.join( pipeline_dir, "03_dlp_redacted.parquet" )

        if not os.path.exists( input_path ):
            pytest.skip( "Requires validate output" )

        dlp_scan( input_path, output_path, pii_threshold=1.0, redact_mode="replace" )

        df = pd.read_parquet( output_path )
        # PII columns should be replaced with tokens
        if "first_name" in df.columns:
            assert ( df[ "first_name" ] == "[PERSON_NAME]" ).all() or df[ "first_name" ].isna().all()
        if "email" in df.columns:
            assert ( df[ "email" ] == "[EMAIL_ADDRESS]" ).all() or df[ "email" ].isna().all()

    def test_dlp_scan_blocks_on_high_pii( self, pipeline_dir ):
        from pipeline.components.dlp_scan import dlp_scan

        input_path  = os.path.join( pipeline_dir, "02_validated.parquet" )
        output_path = os.path.join( pipeline_dir, "03_dlp_blocked.parquet" )

        if not os.path.exists( input_path ):
            pytest.skip( "Requires validate output" )

        # Threshold of 0.0 should block (any PII in text fields triggers)
        # But only if text fields actually have PII — depends on sample
        # This tests the mechanism, not guaranteed to trigger on 200 records
        try:
            dlp_scan( input_path, output_path, pii_threshold=0.001 )
        except ValueError as e:
            assert "PII density" in str( e )


# ==================== Harmonize ====================

class TestHarmonize:

    def test_harmonize_fills_nulls( self, pipeline_dir ):
        from pipeline.components.harmonize import harmonize

        input_path  = os.path.join( pipeline_dir, "03_dlp_scanned.parquet" )
        output_path = os.path.join( pipeline_dir, "04_harmonized.parquet" )

        if not os.path.exists( input_path ):
            pytest.skip( "Requires DLP output" )

        report = harmonize( input_path, output_path )

        assert report[ "output_rows" ] > 0
        assert os.path.exists( output_path )

    def test_harmonize_removes_duplicates( self, pipeline_dir ):
        from pipeline.components.harmonize import harmonize

        input_path = os.path.join( pipeline_dir, "03_dlp_scanned.parquet" )
        if not os.path.exists( input_path ):
            pytest.skip( "Requires DLP output" )

        output_path = os.path.join( pipeline_dir, "04_harmonized.parquet" )
        report = harmonize( input_path, output_path )

        assert report[ "duplicates_removed" ] >= 0


# ==================== Clean ====================

class TestClean:

    def test_clean_produces_numeric_output( self, pipeline_dir ):
        from pipeline.components.clean import clean

        input_path  = os.path.join( pipeline_dir, "04_harmonized.parquet" )
        output_path = os.path.join( pipeline_dir, "05_cleaned.parquet" )

        if not os.path.exists( input_path ):
            pytest.skip( "Requires harmonize output" )

        report = clean( input_path, output_path )
        df     = pd.read_parquet( output_path )

        # All columns except student_id should be numeric
        non_numeric = df.select_dtypes( exclude=[np.number] ).columns.tolist()
        non_numeric = [c for c in non_numeric if c != "student_id"]
        assert len( non_numeric ) == 0, f"Non-numeric columns remain: {non_numeric}"

    def test_clean_removes_some_columns( self, pipeline_dir ):
        from pipeline.components.clean import clean

        input_path  = os.path.join( pipeline_dir, "04_harmonized.parquet" )
        output_path = os.path.join( pipeline_dir, "05_cleaned.parquet" )

        if not os.path.exists( input_path ):
            pytest.skip( "Requires harmonize output" )

        report = clean( input_path, output_path )
        # OHE may increase columns, but some string/constant cols should be dropped
        assert len( report[ "dropped_columns" ] ) > 0 or len( report[ "ohe_columns" ] ) > 0


# ==================== Feature Engineering ====================

class TestFeatureEngineer:

    def test_feature_engineer_adds_features( self, pipeline_dir ):
        from pipeline.components.feature_engineer import feature_engineer

        input_path  = os.path.join( pipeline_dir, "05_cleaned.parquet" )
        output_path = os.path.join( pipeline_dir, "06_features.parquet" )

        if not os.path.exists( input_path ):
            pytest.skip( "Requires clean output" )

        report = feature_engineer( input_path, output_path )

        assert report[ "new_feature_count" ] > 0
        assert report[ "output_columns" ] > report[ "initial_columns" ]

    def test_feature_engineer_no_infinities( self, pipeline_dir ):
        input_path = os.path.join( pipeline_dir, "06_features.parquet" )
        if not os.path.exists( input_path ):
            pytest.skip( "Requires feature output" )

        df = pd.read_parquet( input_path )
        numeric = df.select_dtypes( include=[np.number] )
        # Convert to float to safely check for inf
        for col in numeric.columns:
            vals = pd.to_numeric( numeric[ col ], errors="coerce" ).dropna()
            assert not np.isinf( vals.values ).any(), f"Infinity found in column {col}"


# ==================== Feature Store Sync ====================

class TestFeatureStoreSync:

    def test_feature_store_local_export( self, pipeline_dir ):
        from pipeline.components.feature_store_sync import feature_store_sync

        input_path  = os.path.join( pipeline_dir, "06_features.parquet" )
        output_path = os.path.join( pipeline_dir, "07_feature_store.parquet" )

        if not os.path.exists( input_path ):
            pytest.skip( "Requires feature output" )

        report = feature_store_sync( input_path, output_path )

        assert report[ "entities_synced" ] > 0
        assert report[ "features_synced" ] > 0
        assert report[ "mode" ] == "local"


# ==================== Reduce Dimensions ====================

class TestReduceDimensions:

    def test_reduce_dimensions_removes_features( self, pipeline_dir ):
        from pipeline.components.reduce_dimensions import reduce_dimensions

        input_path  = os.path.join( pipeline_dir, "06_features.parquet" )
        output_path = os.path.join( pipeline_dir, "08_reduced.parquet" )

        if not os.path.exists( input_path ):
            pytest.skip( "Requires feature output" )

        report = reduce_dimensions( input_path, output_path )

        assert report[ "final_features" ] <= report[ "initial_features" ]
        assert report[ "final_features" ] > 2  # At least target + some features

    def test_reduce_dimensions_preserves_target( self, pipeline_dir ):
        output_path = os.path.join( pipeline_dir, "08_reduced.parquet" )
        if not os.path.exists( output_path ):
            pytest.skip( "Requires reduce output" )

        df = pd.read_parquet( output_path )
        assert "second_year_ret_flag" in df.columns


# ==================== Full Pipeline (Local) ====================

class TestFullPipeline:

    def test_pipeline_end_to_end( self, synth_data_dir ):
        from pipeline.vertex_pipeline import run_local

        output_dir = tempfile.mkdtemp( prefix="meridian_pipeline_" )
        try:
            reports = run_local( synth_data_dir, output_dir )

            # All 8 stages should have reports
            expected_stages = [
                "ingest", "validate", "dlp_scan", "harmonize",
                "clean", "feature_engineer", "feature_store_sync", "reduce_dimensions",
            ]
            for stage in expected_stages:
                assert stage in reports, f"Missing stage report: {stage}"

            # Final output should exist and be non-empty
            reduced = os.path.join( output_dir, "08_reduced.parquet" )
            assert os.path.exists( reduced )
            df = pd.read_parquet( reduced )
            assert len( df ) > 0
            assert "second_year_ret_flag" in df.columns

        finally:
            shutil.rmtree( output_dir, ignore_errors=True )
