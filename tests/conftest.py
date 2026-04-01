"""
Pytest configuration for Meridian test suite.

Adds src/ to the Python path so tests can import project modules.
Provides shared fixtures for synthetic data generation.
"""

import os
import sys

import pytest

# Add project src to path
project_root = os.path.dirname( os.path.dirname( os.path.abspath( __file__ ) ) )
src_path     = os.path.join( project_root, "src" )
if src_path not in sys.path:
    sys.path.insert( 0, src_path )


@pytest.fixture( scope="session" )
def small_dataset():
    """Generate a small synthetic dataset (200 students) for testing."""
    from data_synthesis.student_generator import StudentDataGenerator

    gen    = StudentDataGenerator( num_students=200, output_dir="data/test_fixtures", random_seed=42 )
    tables = gen.generate_all()

    # Drop internal latent column
    if "_latent" in tables[ "demographics" ].columns:
        tables[ "demographics" ] = tables[ "demographics" ].drop( columns=["_latent"] )

    yield tables

    # Cleanup
    import shutil
    if os.path.exists( "data/test_fixtures" ):
        shutil.rmtree( "data/test_fixtures" )


@pytest.fixture( scope="session" )
def demographics( small_dataset ):
    """Demographics DataFrame from small dataset."""
    return small_dataset[ "demographics" ]


@pytest.fixture( scope="session" )
def academic_records( small_dataset ):
    """Academic records DataFrame from small dataset."""
    return small_dataset[ "academic_records" ]


@pytest.fixture( scope="session" )
def financial_aid( small_dataset ):
    """Financial aid DataFrame from small dataset."""
    return small_dataset[ "financial_aid" ]


@pytest.fixture( scope="session" )
def enrollment_events( small_dataset ):
    """Enrollment events DataFrame from small dataset."""
    return small_dataset[ "enrollment_events" ]
