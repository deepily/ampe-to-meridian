"""
FastAPI prediction service for student retention model.

Custom prediction container that wraps the trained model
with a REST API documented via OpenAPI/Cloud Endpoints.

Demonstrates API Design & Versioning competency.

Requires:
    - Trained model pickle in MODEL_PATH
    - FastAPI, uvicorn installed

Ensures:
    - /predict endpoint accepts student features, returns retention prediction
    - /health endpoint for load balancer health checks
    - OpenAPI spec auto-generated at /docs
"""

import os
import pickle
import time
from typing import Optional

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from utils.logging_config import get_logger

logger = get_logger( __name__, component="serving" )

# ---- App Configuration ----

MODEL_PATH = os.environ.get( "MODEL_PATH", "data/pipeline_output/training/random_forest_none.pkl" )

app = FastAPI(
    title="Meridian Retention Prediction API",
    description="Predicts second-year student retention probability. Part of the Meridian GCP-native ML pipeline.",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/api/v1/openapi.json",
)

# Model loaded at startup
_model = None


# ---- Request/Response Models ----

class PredictionRequest( BaseModel ):
    """Student features for retention prediction."""
    student_id          : str            = Field( ..., description="Unique student identifier" )
    hs_gpa              : Optional[float] = Field( None, ge=0.0, le=4.0, description="High school GPA" )
    sat_score           : Optional[float] = Field( None, ge=400, le=1600, description="SAT composite score" )
    cumulative_gpa      : Optional[float] = Field( None, ge=0.0, le=4.0 )
    credits_earned      : Optional[int]   = Field( None, ge=0 )
    credits_attempted   : Optional[int]   = Field( None, ge=0 )
    efc                 : Optional[float] = Field( None, ge=0, description="Expected Family Contribution" )
    total_aid_amount    : Optional[float] = Field( None, ge=0 )
    loan_amount         : Optional[float] = Field( None, ge=0 )
    campus_distance_miles: Optional[float] = Field( None, ge=0 )
    first_generation_flag: Optional[bool]  = Field( None )
    pell_eligible       : Optional[bool]   = Field( None )


class PredictionResponse( BaseModel ):
    """Retention prediction result."""
    student_id          : str
    predicted_class     : int   = Field( ..., description="0=not retained, 1=retained" )
    retention_probability: float = Field( ..., ge=0.0, le=1.0 )
    model_version       : str
    latency_ms          : float


class HealthResponse( BaseModel ):
    """Health check response."""
    status       : str
    model_loaded : bool
    model_path   : str


# ---- Endpoints ----

@app.on_event( "startup" )
async def load_model():
    """Load model at startup."""
    global _model

    if os.path.exists( MODEL_PATH ):
        with open( MODEL_PATH, "rb" ) as f:
            _model = pickle.load( f )
        logger.info( f"Model loaded from {MODEL_PATH}" )
    else:
        logger.warning( f"Model not found at {MODEL_PATH}. Predictions will fail." )


@app.get( "/health", response_model=HealthResponse, tags=["System"] )
async def health():
    """Health check for load balancer."""
    return HealthResponse(
        status="healthy" if _model is not None else "degraded",
        model_loaded=_model is not None,
        model_path=MODEL_PATH,
    )


@app.post( "/api/v1/predict", response_model=PredictionResponse, tags=["Prediction"] )
async def predict( request: PredictionRequest ):
    """
    Predict student retention probability.

    Returns a retention prediction (0/1) with probability score.
    """
    if _model is None:
        raise HTTPException( status_code=503, detail="Model not loaded" )

    start_time = time.time()

    # Build feature vector from request
    features = _request_to_features( request )

    try:
        prediction  = int( _model.predict( features )[ 0 ] )
        probability = float( _model.predict_proba( features )[ 0, 1 ] ) if hasattr( _model, "predict_proba" ) else float( prediction )
    except Exception as e:
        logger.error( f"Prediction failed: {e}" )
        raise HTTPException( status_code=500, detail=f"Prediction error: {str( e )}" )

    latency_ms = ( time.time() - start_time ) * 1000

    return PredictionResponse(
        student_id=request.student_id,
        predicted_class=prediction,
        retention_probability=round( probability, 4 ),
        model_version="v1",
        latency_ms=round( latency_ms, 2 ),
    )


def _request_to_features( request: PredictionRequest ) -> np.ndarray:
    """
    Convert API request to feature array matching model's expected input.

    Uses default values for missing features to match training pipeline.
    """
    import pandas as pd

    # Build a single-row DataFrame with the features the model expects
    row = {
        "hs_gpa"               : request.hs_gpa or -1.0,
        "sat_score"            : request.sat_score or -1.0,
        "cumulative_gpa"       : request.cumulative_gpa or -1.0,
        "credits_earned"       : request.credits_earned or -1,
        "credits_attempted"    : request.credits_attempted or -1,
        "efc"                  : request.efc or -1.0,
        "total_aid_amount"     : request.total_aid_amount or -1.0,
        "loan_amount"          : request.loan_amount or -1.0,
        "campus_distance_miles": request.campus_distance_miles or -1.0,
        "first_generation_flag": int( request.first_generation_flag ) if request.first_generation_flag is not None else 0,
        "pell_eligible"        : int( request.pell_eligible ) if request.pell_eligible is not None else 0,
    }

    # Add derived features that the model expects
    if row[ "cumulative_gpa" ] > 0 and row[ "hs_gpa" ] > 0:
        row[ "gpa_change" ] = row[ "cumulative_gpa" ] - row[ "hs_gpa" ]
    else:
        row[ "gpa_change" ] = -1.0

    if row[ "credits_attempted" ] > 0:
        row[ "credit_ratio" ] = row[ "credits_earned" ] / row[ "credits_attempted" ]
    else:
        row[ "credit_ratio" ] = 0.0

    df = pd.DataFrame( [row] )

    # Ensure columns match model — add missing columns as 0, drop extras
    if hasattr( _model, "feature_names_in_" ):
        expected = list( _model.feature_names_in_ )
        for col in expected:
            if col not in df.columns:
                df[ col ] = 0
        df = df[ expected ]

    return df


# ---- CLI Entry Point ----

if __name__ == "__main__":
    import uvicorn
    uvicorn.run( app, host="0.0.0.0", port=8080 )
