"""
Structured Cloud Logging configuration for Meridian pipeline.

Sets up Python logging to emit structured JSON logs compatible with
Cloud Logging. Falls back to standard console logging when running locally.

Requires:
    - google-cloud-logging (optional, for GCP integration)

Ensures:
    - Logger emits structured JSON with severity, component, and trace fields
    - Works locally without GCP credentials (console fallback)
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone


class StructuredFormatter( logging.Formatter ):
    """
    Formats log records as structured JSON for Cloud Logging.

    Output format matches Cloud Logging's expected JSON payload structure
    so log entries are parsed with correct severity and labels.
    """

    def __init__( self, component: str = "meridian" ):
        super().__init__()
        self.component = component

    def format( self, record ):

        log_entry = {
            "severity"    : record.levelname,
            "message"     : record.getMessage(),
            "component"   : self.component,
            "timestamp"   : datetime.now( timezone.utc ).isoformat(),
            "logger"      : record.name,
            "source"      : f"{record.pathname}:{record.lineno}",
        }

        if hasattr( record, "trace_id" ):
            log_entry[ "logging.googleapis.com/trace" ] = record.trace_id

        if hasattr( record, "span_id" ):
            log_entry[ "logging.googleapis.com/spanId" ] = record.span_id

        if record.exc_info:
            log_entry[ "exception" ] = self.formatException( record.exc_info )

        return json.dumps( log_entry )


def get_logger( name: str, component: str = None, level: int = logging.INFO ) -> logging.Logger:
    """
    Get a structured logger for pipeline components.

    Requires:
        - name is a non-empty string (typically __name__)

    Ensures:
        - Returns a logger with structured JSON formatting
        - component is auto-derived from the last dotted segment of name
          (e.g. "pipeline.components.clean" -> "clean") when not passed
        - Uses Cloud Logging handler if available, else console
    """
    if component is None:
        component = name.split( "." )[-1] if "." in name else "meridian"

    logger = logging.getLogger( name )

    if logger.handlers:
        return logger

    logger.setLevel( level )

    # Try Cloud Logging first, fall back to console
    try:
        if os.environ.get( "USE_CLOUD_LOGGING", "" ).lower() == "true":
            import google.cloud.logging
            client = google.cloud.logging.Client()
            client.setup_logging( log_level=level )
            return logger
    except ImportError:
        pass

    # Console handler with structured JSON
    handler = logging.StreamHandler( sys.stdout )
    handler.setFormatter( StructuredFormatter( component=component ) )
    logger.addHandler( handler )

    return logger
