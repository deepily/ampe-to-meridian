"""
OpenTelemetry integration for Meridian pipeline.

Provides tracing (Cloud Trace) and metrics (Cloud Monitoring) via
OpenTelemetry SDK with GCP exporters.

Requires:
    - opentelemetry-api, opentelemetry-sdk installed
    - opentelemetry-exporter-gcp-trace, opentelemetry-exporter-gcp-monitoring installed
    - GCP credentials configured (for exporters)

Ensures:
    - Tracer and meter available for pipeline instrumentation
    - @traced decorator for automatic span creation
    - Falls back gracefully when GCP exporters unavailable
"""

import functools
import os
from typing import Optional

from utils.logging_config import get_logger

logger = get_logger( __name__ )

_tracer = None
_meter  = None


def init_telemetry(
    project_id   : str,
    service_name : str = "meridian-pipeline",
    use_gcp      : bool = True,
):
    """
    Initialize OpenTelemetry with optional GCP exporters.

    Requires:
        - project_id is a valid GCP project ID
        - service_name identifies this service in traces

    Ensures:
        - Global tracer and meter configured
        - GCP exporters active if use_gcp=True and credentials available
    """
    global _tracer, _meter

    try:
        from opentelemetry import trace, metrics
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create( {
            "service.name"       : service_name,
            "service.namespace"  : "meridian",
            "gcp.project_id"     : project_id,
        } )

        # ---- Tracing ----
        tracer_provider = TracerProvider( resource=resource )

        if use_gcp:
            try:
                from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
                tracer_provider.add_span_processor(
                    _get_batch_processor( CloudTraceSpanExporter( project_id=project_id ) )
                )
                logger.info( "Cloud Trace exporter configured" )
            except ImportError:
                logger.warning( "Cloud Trace exporter not available" )

        trace.set_tracer_provider( tracer_provider )
        _tracer = trace.get_tracer( service_name )

        # ---- Metrics ----
        meter_provider = MeterProvider( resource=resource )

        if use_gcp:
            try:
                from opentelemetry.exporter.cloud_monitoring import CloudMonitoringMetricsExporter
                from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
                reader = PeriodicExportingMetricReader(
                    CloudMonitoringMetricsExporter( project_id=project_id ),
                    export_interval_millis=60000,
                )
                meter_provider = MeterProvider( resource=resource, metric_readers=[ reader ] )
                logger.info( "Cloud Monitoring metrics exporter configured" )
            except ImportError:
                logger.warning( "Cloud Monitoring exporter not available" )

        metrics.set_meter_provider( meter_provider )
        _meter = metrics.get_meter( service_name )

        logger.info( f"OpenTelemetry initialized for {service_name} (GCP={use_gcp})" )

    except ImportError as e:
        logger.warning( f"OpenTelemetry SDK not available: {e}" )


def _get_batch_processor( exporter ):
    """
    Create a BatchSpanProcessor for the given exporter.

    Requires:
        - exporter is a valid OpenTelemetry SpanExporter

    Ensures:
        - Returns a BatchSpanProcessor wrapping the exporter
    """
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    return BatchSpanProcessor( exporter )


def get_tracer():
    """
    Get the configured tracer.

    Ensures:
        - Returns the global tracer, or a no-op tracer if not initialized
    """
    if _tracer is not None:
        return _tracer

    try:
        from opentelemetry import trace
        return trace.get_tracer( "meridian-pipeline" )
    except ImportError:
        return None


def get_meter():
    """
    Get the configured meter.

    Ensures:
        - Returns the global meter, or None if not initialized
    """
    if _meter is not None:
        return _meter

    try:
        from opentelemetry import metrics
        return metrics.get_meter( "meridian-pipeline" )
    except ImportError:
        return None


def traced( name: Optional[str] = None ):
    """
    Decorator for automatic span creation around pipeline functions.

    Requires:
        - name is an optional string for the span name (defaults to func.__name__)

    Ensures:
        - Function wrapped in an OpenTelemetry span
        - Span attributes set for component name, status, and errors
        - Falls back to direct execution if tracer unavailable

    Usage:
        @traced( "ingest_data" )
        def ingest_from_bigquery( ... ):
            ...
    """
    def decorator( func ):
        @functools.wraps( func )
        def wrapper( *args, **kwargs ):
            tracer    = get_tracer()
            span_name = name or func.__name__

            if tracer is not None:
                with tracer.start_as_current_span( span_name ) as span:
                    span.set_attribute( "meridian.component", span_name )
                    try:
                        result = func( *args, **kwargs )
                        span.set_attribute( "meridian.status", "success" )
                        return result
                    except Exception as e:
                        span.set_attribute( "meridian.status", "error" )
                        span.set_attribute( "meridian.error", str( e ) )
                        raise
            else:
                return func( *args, **kwargs )

        return wrapper
    return decorator
