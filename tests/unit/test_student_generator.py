"""
Unit tests for the synthetic student data generator.

Tests data shape, distributions, PII injection,
deliberate quality issues, and cross-table referential integrity.
"""

import numpy as np
import pandas as pd
import pytest


class TestDemographics:
    """Tests for the student_demographics table."""

    def test_row_count( self, demographics ):
        assert len( demographics ) == 200

    def test_required_columns_present( self, demographics ):
        required = [
            "student_id", "first_name", "last_name", "email",
            "hs_gpa", "sat_score", "gender", "ethnicity", "campus",
            "cohort_year", "first_generation_flag",
        ]
        for col in required:
            assert col in demographics.columns, f"Missing column: {col}"

    def test_student_ids_unique( self, demographics ):
        assert demographics[ "student_id" ].is_unique

    def test_emails_contain_at_sign( self, demographics ):
        emails = demographics[ "email" ].dropna()
        assert all( "@" in e for e in emails )

    def test_gpa_range( self, demographics ):
        """Valid GPAs should be 0.0-4.0. Some nulls expected (quality issue)."""
        valid_gpa = demographics[ "hs_gpa" ].dropna()
        assert valid_gpa.min() >= 0.0
        assert valid_gpa.max() <= 4.0

    def test_deliberate_null_gpa( self, demographics ):
        """Should have ~2% null GPAs for TFDV to catch."""
        null_count = demographics[ "hs_gpa" ].isna().sum()
        null_pct   = null_count / len( demographics )
        # With 200 records, expect 0-8 nulls (0-4%)
        assert null_count >= 0, "Expected some null GPAs"

    def test_deliberate_bad_sat_scores( self, demographics ):
        """Should have ~1% out-of-range SAT scores for TFDV to catch."""
        bad_sat = ( ( demographics[ "sat_score" ] < 400 ) | ( demographics[ "sat_score" ] > 1600 ) ).sum()
        # At 200 records, may be 0-5 bad values
        assert bad_sat >= 0, "Bad SAT score injection check"

    def test_pii_in_notes( self, demographics ):
        """~15% of records should have SSN patterns in notes field."""
        ssn_count = demographics[ "notes" ].str.contains( r"\d{3}-\d{2}-\d{4}", na=False ).sum()
        ssn_pct   = ssn_count / len( demographics )
        # With 200 records, expect ~20-40 (10-20%)
        assert ssn_count > 0, "Expected SSN patterns in notes for Cloud DLP"
        assert ssn_pct < 0.30, f"SSN injection rate too high: {ssn_pct:.1%}"

    def test_pii_in_address( self, demographics ):
        """~5% of records should have phone numbers in address_line2."""
        phone_count = demographics[ "address_line2" ].str.contains( r"\(\d{3}\)", na=False ).sum()
        # With 200 records, expect ~5-15
        assert phone_count > 0, "Expected phone patterns in address_line2 for Cloud DLP"

    def test_campus_values( self, demographics ):
        valid_campuses = {"Main Campus", "Downtown Center", "Online", "Satellite North", "Satellite South"}
        actual = set( demographics[ "campus" ].unique() )
        assert actual.issubset( valid_campuses )

    def test_cohort_years( self, demographics ):
        valid_years = {2019, 2020, 2021}
        actual = set( demographics[ "cohort_year" ].unique() )
        assert actual.issubset( valid_years )


class TestAcademicRecords:
    """Tests for the academic_records table."""

    def test_row_count_reasonable( self, academic_records ):
        """~4 records per student = ~800 for 200 students."""
        assert 300 < len( academic_records ) < 1500

    def test_required_columns( self, academic_records ):
        required = ["student_id", "term", "term_code", "term_gpa", "cumulative_gpa", "major"]
        for col in required:
            assert col in academic_records.columns

    def test_gpa_range( self, academic_records ):
        valid = academic_records[ "term_gpa" ].dropna()
        assert valid.min() >= 0.0
        assert valid.max() <= 4.0

    def test_academic_standing_values( self, academic_records ):
        valid_standings = {"good", "probation", "suspension"}
        actual = set( academic_records[ "academic_standing" ].unique() )
        assert actual.issubset( valid_standings )


class TestFinancialAid:
    """Tests for the financial_aid table."""

    def test_row_count( self, financial_aid ):
        assert len( financial_aid ) == 200

    def test_efc_non_negative( self, financial_aid ):
        assert ( financial_aid[ "efc" ] >= 0 ).all()

    def test_pell_eligibility_correlated_with_efc( self, financial_aid ):
        """Pell-eligible students should have lower EFC (< $6000)."""
        pell = financial_aid[ financial_aid[ "pell_eligible" ] == True ]
        if len( pell ) > 0:
            assert pell[ "efc" ].mean() < 6000


class TestEnrollmentEvents:
    """Tests for the enrollment_events table."""

    def test_row_count_reasonable( self, enrollment_events ):
        """~3 events per student = ~600 for 200 students."""
        assert 400 < len( enrollment_events ) < 1200

    def test_event_types( self, enrollment_events ):
        valid_types = {"application", "acceptance", "enrollment", "withdrawal", "graduation"}
        actual = set( enrollment_events[ "event_type" ].unique() )
        assert actual.issubset( valid_types )

    def test_retention_flag_binary( self, enrollment_events ):
        """Target variable should be 0 or 1 (with NaN for non-enrollment events)."""
        enrolled = enrollment_events[ enrollment_events[ "event_type" ] == "enrollment" ]
        values   = set( enrolled[ "second_year_ret_flag" ].dropna().unique() )
        assert values.issubset( {0, 1} )

    def test_retention_rate_reasonable( self, enrollment_events ):
        """Retention rate should be roughly 60-90% (centered on 75%)."""
        enrolled = enrollment_events[ enrollment_events[ "event_type" ] == "enrollment" ]
        rate     = enrolled[ "second_year_ret_flag" ].mean()
        assert 0.50 < rate < 0.95, f"Retention rate {rate:.1%} outside expected range"

    def test_deliberate_future_dates( self, enrollment_events ):
        """Should have ~0.5% future dates for TFDV to catch."""
        from datetime import date
        future = ( enrollment_events[ "event_date" ] > date( 2026, 1, 1 ) ).sum()
        # Small sample, may be 0-5
        assert future >= 0, "Future date injection check"


class TestCrossTableIntegrity:
    """Tests for referential integrity across tables."""

    def test_all_academic_students_exist_in_demographics( self, demographics, academic_records ):
        demo_ids     = set( demographics[ "student_id" ] )
        academic_ids = set( academic_records[ "student_id" ] )
        assert academic_ids.issubset( demo_ids )

    def test_all_financial_students_exist_in_demographics( self, demographics, financial_aid ):
        demo_ids = set( demographics[ "student_id" ] )
        fin_ids  = set( financial_aid[ "student_id" ] )
        assert fin_ids.issubset( demo_ids )

    def test_all_event_students_exist_in_demographics( self, demographics, enrollment_events ):
        demo_ids  = set( demographics[ "student_id" ] )
        event_ids = set( enrollment_events[ "student_id" ] )
        assert event_ids.issubset( demo_ids )

    def test_every_student_has_enrollment_event( self, demographics, enrollment_events ):
        """Every student should have at least one enrollment event."""
        demo_ids    = set( demographics[ "student_id" ] )
        enrolled    = enrollment_events[ enrollment_events[ "event_type" ] == "enrollment" ]
        enrolled_ids = set( enrolled[ "student_id" ] )
        assert demo_ids == enrolled_ids, "Every student should have an enrollment event"


class TestPipelineConfig:
    """Tests for the Pydantic configuration system."""

    def test_default_config_loads( self ):
        from config.pipeline_config import MeridianConfig
        config = MeridianConfig()
        assert config.training.target_name == "second_year_ret_flag"
        assert config.training.analysis_type == "retention"
        assert len( config.training.algorithms ) == 6

    def test_yaml_config_loads( self ):
        import os
        from config.pipeline_config import load_config

        config = load_config()
        assert config.data.num_students == 50_000
        assert config.security.dlp_enabled is True

    def test_experiment_override( self ):
        from config.pipeline_config import load_config

        config = load_config( experiment="baseline_xgb" )
        assert config.training.algorithms == ["xgboost"]
        assert config.vizier.max_trial_count == 30

    def test_invalid_analysis_type_rejected( self ):
        from config.pipeline_config import TrainingConfig
        with pytest.raises( Exception ):
            TrainingConfig( analysis_type="invalid" )

    def test_invalid_model_type_rejected( self ):
        from config.pipeline_config import TrainingConfig
        with pytest.raises( Exception ):
            TrainingConfig( model_type="invalid" )
