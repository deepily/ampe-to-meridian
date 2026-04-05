"""
Graceful degradation logic for prediction serving.

Implements a 3-tier fallback strategy:
1. Live model prediction (primary)
2. Cached prediction from Memorystore (if model unavailable)
3. Batch predictions from GCS (if cache miss and model down)

Demonstrates Graceful Degradation competency.

Requires:
    - PredictionCache instance
    - Batch predictions file (from deploy stage)

Ensures:
    - Always returns a prediction (never fails silently)
    - Response includes served_from field indicating source
"""

import os
from typing import Optional

import pandas as pd

from utils.logging_config import get_logger

logger = get_logger( __name__ )


class FallbackPredictor:
    """
    3-tier fallback prediction with degradation tracking.

    Requires:
        - cache: PredictionCache instance
        - batch_predictions_path: path to Parquet with pre-computed predictions

    Ensures:
        - predict() always returns a result dict
        - Tracks which tier served each prediction
    """

    def __init__(
        self,
        cache,
        batch_predictions_path : Optional[str] = None,
        model                  = None,
    ):
        self.cache      = cache
        self.model       = model
        self._batch_df   = None
        self._tier_counts = { "live": 0, "cache": 0, "batch": 0, "default": 0 }

        if batch_predictions_path and os.path.exists( batch_predictions_path ):
            self._batch_df = pd.read_parquet( batch_predictions_path )
            self._batch_df = self._batch_df.set_index( "student_id" ) if "student_id" in self._batch_df.columns else self._batch_df
            logger.info( f"Batch predictions loaded: {len( self._batch_df ):,} rows" )

    def predict( self, student_id: str, features: dict = None ) -> dict:
        """
        Get prediction with 3-tier fallback.

        Requires:
            - student_id is a non-empty string

        Ensures:
            - Returns dict with predicted_class, probability, served_from
            - served_from is one of: 'live', 'cache', 'batch', 'default'
        """

        # Tier 1: Live model prediction
        if self.model is not None and features is not None:
            try:
                result = self._predict_live( student_id, features )
                self.cache.set( student_id, result )
                self._tier_counts[ "live" ] += 1
                return result
            except Exception as e:
                logger.warning( f"Live prediction failed for {student_id}: {e}" )

        # Tier 2: Cached prediction
        cached = self.cache.get( student_id )
        if cached is not None:
            cached[ "served_from" ] = "cache"
            self._tier_counts[ "cache" ] += 1
            return cached

        # Tier 3: Batch predictions from GCS
        if self._batch_df is not None and student_id in self._batch_df.index:
            batch_result = self._predict_from_batch( student_id )
            self._tier_counts[ "batch" ] += 1
            return batch_result

        # Tier 4: Default (model and all fallbacks unavailable)
        self._tier_counts[ "default" ] += 1
        logger.warning( f"All prediction tiers failed for {student_id}. Returning default." )
        return {
            "student_id"           : student_id,
            "predicted_class"      : -1,
            "retention_probability": 0.5,
            "served_from"          : "default",
            "degraded"             : True,
            "model_version"        : "none",
        }

    def _predict_live( self, student_id: str, features: dict ) -> dict:
        """Tier 1: Live model prediction."""
        import numpy as np

        feature_values = np.array( [list( features.values() )] )
        prediction     = int( self.model.predict( feature_values )[ 0 ] )
        probability    = float( self.model.predict_proba( feature_values )[ 0, 1 ] ) if hasattr( self.model, "predict_proba" ) else float( prediction )

        return {
            "student_id"           : student_id,
            "predicted_class"      : prediction,
            "retention_probability": round( probability, 4 ),
            "served_from"          : "live",
            "degraded"             : False,
            "model_version"        : "v1",
        }

    def _predict_from_batch( self, student_id: str ) -> dict:
        """Tier 3: Batch prediction from pre-computed file."""
        row = self._batch_df.loc[ student_id ]

        return {
            "student_id"           : student_id,
            "predicted_class"      : int( row.get( "predicted_class", -1 ) ),
            "retention_probability": float( row.get( "predicted_probability", 0.5 ) ),
            "served_from"          : "batch",
            "degraded"             : True,
            "model_version"        : str( row.get( "model_version", "batch" ) ),
        }

    def stats( self ) -> dict:
        """Return fallback tier statistics."""
        total = sum( self._tier_counts.values() )
        return {
            "tier_counts"   : self._tier_counts.copy(),
            "total_requests": total,
            "degraded_pct"  : round(
                ( self._tier_counts[ "cache" ] + self._tier_counts[ "batch" ] + self._tier_counts[ "default" ] ) / total, 4
            ) if total > 0 else 0.0,
            "cache_stats"   : self.cache.stats(),
        }
