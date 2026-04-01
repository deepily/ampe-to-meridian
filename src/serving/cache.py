"""
Prediction cache using Memorystore (Redis) or local dict fallback.

Caches predictions by student_id to serve repeat requests without
hitting the model. Demonstrates Graceful Degradation competency.

Requires:
    - Redis connection (Memorystore) or local mode

Ensures:
    - Cache hit returns prediction without model inference
    - Cache miss triggers model inference and stores result
    - TTL-based expiration (configurable)
"""

import json
import time
from typing import Optional

from utils.logging_config import get_logger

logger = get_logger( __name__, component="cache" )


class PredictionCache:
    """
    Prediction cache with Redis backend and local dict fallback.

    Requires:
        - For Redis: redis-py installed, Memorystore instance running
        - For local: no dependencies

    Ensures:
        - get() returns cached prediction or None
        - set() stores prediction with TTL
        - stats() returns hit/miss counts
    """

    def __init__(
        self,
        redis_host : Optional[str] = None,
        redis_port : int = 6379,
        ttl_seconds: int = 3600,
    ):
        self.ttl_seconds = ttl_seconds
        self._hits       = 0
        self._misses     = 0
        self._redis      = None
        self._local      = {}

        if redis_host:
            try:
                import redis
                self._redis = redis.Redis( host=redis_host, port=redis_port, decode_responses=True )
                self._redis.ping()
                logger.info( f"Redis cache connected: {redis_host}:{redis_port}" )
            except Exception as e:
                logger.warning( f"Redis connection failed ({e}). Using local cache." )
                self._redis = None
        else:
            logger.info( "Using local in-memory cache (no Redis configured)" )

    def get( self, student_id: str ) -> Optional[dict]:
        """
        Get cached prediction for student.

        Ensures:
            - Returns dict with prediction data or None if not cached
            - Increments hit/miss counters
        """
        key = f"pred:{student_id}"

        if self._redis:
            try:
                data = self._redis.get( key )
                if data:
                    self._hits += 1
                    return json.loads( data )
            except Exception as e:
                logger.warning( f"Redis get failed: {e}" )

        # Local fallback
        if key in self._local:
            entry = self._local[ key ]
            if time.time() - entry[ "timestamp" ] < self.ttl_seconds:
                self._hits += 1
                return entry[ "data" ]
            else:
                del self._local[ key ]

        self._misses += 1
        return None

    def set( self, student_id: str, prediction: dict ):
        """
        Cache a prediction for student.

        Ensures:
            - Prediction stored with TTL in Redis or local dict
        """
        key  = f"pred:{student_id}"
        data = json.dumps( prediction, default=str )

        if self._redis:
            try:
                self._redis.setex( key, self.ttl_seconds, data )
                return
            except Exception as e:
                logger.warning( f"Redis set failed: {e}" )

        # Local fallback
        self._local[ key ] = {
            "data"      : prediction,
            "timestamp" : time.time(),
        }

    def stats( self ) -> dict:
        """Return cache performance statistics."""
        total = self._hits + self._misses
        return {
            "hits"      : self._hits,
            "misses"    : self._misses,
            "hit_rate"  : round( self._hits / total, 4 ) if total > 0 else 0.0,
            "mode"      : "redis" if self._redis else "local",
            "ttl"       : self.ttl_seconds,
            "local_size": len( self._local ),
        }

    def clear( self ):
        """Clear all cached predictions."""
        if self._redis:
            try:
                # Only clear prediction keys
                for key in self._redis.scan_iter( "pred:*" ):
                    self._redis.delete( key )
            except Exception:
                pass
        self._local.clear()
        self._hits   = 0
        self._misses = 0
