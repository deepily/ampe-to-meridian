"""
Pydantic-based pipeline configuration for Meridian.

Replaces AMPE's INI-based ConfigurationManager with typed,
validated YAML configuration using Pydantic v2 BaseSettings.

Configuration hierarchy (highest precedence first):
    1. Environment variables (MERIDIAN_*)
    2. Experiment-specific YAML overrides
    3. defaults.yaml
    4. Pydantic field defaults

Requires:
    - pydantic >= 2.5.0
    - pydantic-settings >= 2.1.0
    - pyyaml >= 6.0

Ensures:
    - All config values are type-validated
    - Invalid values raise ValidationError at load time
    - Experiment overrides are cleanly merged with defaults
"""

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings


# ---- Sub-Models ----

class DataConfig( BaseModel ):
    """Configuration for data sources and synthesis."""
    project_id          : str   = Field( default="REPLACE_WITH_PROJECT_ID", description="GCP project ID" )
    dataset_id          : str   = Field( default="meridian_student_data_dev", description="BigQuery dataset ID" )
    training_bucket     : str   = Field( default="meridian-training-data-dev", description="GCS bucket for training data" )
    artifacts_bucket    : str   = Field( default="meridian-artifacts-dev", description="GCS bucket for pipeline artifacts" )
    region              : str   = Field( default="us-central1", description="GCP region" )
    num_students        : int   = Field( default=50_000, ge=100 )
    retention_rate      : float = Field( default=0.75, gt=0.0, lt=1.0 )
    random_seed         : int   = Field( default=42, ge=0 )


class PipelineConfig( BaseModel ):
    """Configuration for Vertex AI Pipeline execution."""
    pipeline_name       : str   = Field( default="meridian-retention-pipeline" )
    pipeline_root       : str   = Field( default="gs://meridian-artifacts-dev/pipeline_root" )
    service_account     : str   = Field( default="" )
    enable_caching      : bool  = Field( default=True )
    experiment_name     : str   = Field( default="meridian-baseline" )


class TrainingConfig( BaseModel ):
    """Configuration for model training and competition."""
    analysis_type       : str   = Field( default="retention" )
    model_type          : str   = Field( default="classification" )
    target_name         : str   = Field( default="second_year_ret_flag" )
    algorithms          : list  = Field( default=["xgboost", "random_forest", "logistic_regression", "adaboost", "decision_tree", "gradient_boosting"] )
    smote_strategies    : list  = Field( default=["none", "smote"] )
    smote_which_rate    : str   = Field( default="tn" )
    competition_metric  : str   = Field( default="tn" )
    test_size           : float = Field( default=0.2, gt=0.0, lt=1.0 )
    cross_val_folds     : int   = Field( default=5, ge=2 )

    @field_validator( "analysis_type" )
    @classmethod
    def validate_analysis_type( cls, v ):
        if v not in ["retention", "persistence"]:
            raise ValueError( "analysis_type must be 'retention' or 'persistence'" )
        return v

    @field_validator( "model_type" )
    @classmethod
    def validate_model_type( cls, v ):
        if v not in ["classification", "regression"]:
            raise ValueError( "model_type must be 'classification' or 'regression'" )
        return v


class VizierConfig( BaseModel ):
    """Configuration for Vertex AI Vizier hyperparameter tuning."""
    enabled             : bool  = Field( default=True )
    max_trial_count     : int   = Field( default=20, ge=1 )
    parallel_trial_count: int   = Field( default=3, ge=1 )
    algorithm           : str   = Field( default="xgboost", description="Algorithm to tune with Vizier" )


class SecurityConfig( BaseModel ):
    """Configuration for DLP, encryption, and compliance."""
    dlp_enabled           : bool  = Field( default=True )
    dlp_inspect_template  : str   = Field( default="" )
    dlp_deidentify_template: str  = Field( default="" )
    dlp_pii_threshold     : float = Field( default=0.05, description="Max PII density before pipeline blocks" )


class MonitoringConfig( BaseModel ):
    """Configuration for model monitoring and observability."""
    model_monitoring_enabled : bool  = Field( default=True )
    drift_threshold_js       : float = Field( default=0.1, description="Jensen-Shannon divergence threshold" )
    skew_threshold           : float = Field( default=0.1, description="Training-serving skew threshold" )
    prediction_log_table     : str   = Field( default="prediction_log" )
    alerting_enabled         : bool  = Field( default=True )


class DimensionalityConfig( BaseModel ):
    """Configuration for feature selection and dimensionality reduction."""
    correlation_threshold   : float = Field( default=0.85, gt=0.0, le=1.0 )
    vif_threshold           : float = Field( default=10.0, gt=0.0 )
    correlation_method      : str   = Field( default="pearson" )
    skip_columns            : list  = Field( default=["campus_longitude", "campus_latitude"] )


# ---- Root Configuration ----

class MeridianConfig( BaseSettings ):
    """
    Root configuration for the Meridian pipeline.

    Loads from YAML files + environment variables.
    Env vars use MERIDIAN_ prefix (e.g., MERIDIAN_DATA__PROJECT_ID).
    """
    data            : DataConfig           = Field( default_factory=DataConfig )
    pipeline        : PipelineConfig       = Field( default_factory=PipelineConfig )
    training        : TrainingConfig       = Field( default_factory=TrainingConfig )
    vizier          : VizierConfig         = Field( default_factory=VizierConfig )
    security        : SecurityConfig       = Field( default_factory=SecurityConfig )
    monitoring      : MonitoringConfig     = Field( default_factory=MonitoringConfig )
    dimensionality  : DimensionalityConfig = Field( default_factory=DimensionalityConfig )

    model_config = {
        "env_prefix"       : "MERIDIAN_",
        "env_nested_delimiter" : "__",
    }

    @classmethod
    def from_yaml( cls, defaults_path: str, experiment_path: Optional[str] = None ) -> "MeridianConfig":
        """
        Load configuration from YAML files with optional experiment override.

        Requires:
            - defaults_path points to a valid YAML file

        Ensures:
            - Returns a fully validated MeridianConfig
            - Experiment values override defaults where specified
        """
        with open( defaults_path, "r" ) as f:
            defaults = yaml.safe_load( f ) or {}

        if experiment_path and os.path.exists( experiment_path ):
            with open( experiment_path, "r" ) as f:
                overrides = yaml.safe_load( f ) or {}
            defaults = _deep_merge( defaults, overrides )

        return cls( **defaults )


def _deep_merge( base: dict, override: dict ) -> dict:
    """Deep merge two dicts. Override values take precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance( result[ key ], dict ) and isinstance( value, dict ):
            result[ key ] = _deep_merge( result[ key ], value )
        else:
            result[ key ] = value
    return result


# ---- Default Config Loader ----

def load_config( experiment: Optional[str] = None ) -> MeridianConfig:
    """
    Convenience function to load config from standard locations.

    Requires:
        - src/config/defaults.yaml exists relative to project root

    Ensures:
        - Returns validated MeridianConfig instance
    """
    config_dir      = Path( __file__ ).parent
    defaults_path   = config_dir / "defaults.yaml"
    experiment_path = config_dir / "experiments" / f"{experiment}.yaml" if experiment else None

    if defaults_path.exists():
        return MeridianConfig.from_yaml(
            str( defaults_path ),
            str( experiment_path ) if experiment_path else None,
        )
    else:
        return MeridianConfig()


if __name__ == "__main__":
    config = load_config()
    print( config.model_dump_json( indent=2 ) )
