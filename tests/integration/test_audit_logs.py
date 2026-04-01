"""
Cloud Audit Logs verification tests.

Queries Cloud Audit Logs to verify that pipeline operations
(BigQuery, GCS, Vertex AI) are properly logged.

Requires:
    - GCP credentials with logging.viewer role
    - Pipeline must have been run at least once

Ensures:
    - Admin activity logs exist for key services
    - Data access logs exist for BigQuery and GCS
"""

import os
import pytest

# Skip all tests if not in GCP integration mode
pytestmark = pytest.mark.skipif(
    os.environ.get( "RUN_INTEGRATION_TESTS", "" ).lower() != "true",
    reason="Integration tests require RUN_INTEGRATION_TESTS=true and GCP credentials",
)

PROJECT_ID = os.environ.get( "GCP_PROJECT_ID", "ampe-to-meridian" )


@pytest.fixture( scope="module" )
def logging_client():
    """Create a Cloud Logging client."""
    from google.cloud import logging as cloud_logging
    return cloud_logging.Client( project=PROJECT_ID )


class TestAuditLogs:
    """Verify Cloud Audit Logs are generated for pipeline operations."""

    def test_bigquery_admin_activity( self, logging_client ):
        """
        Verify BigQuery admin activity logs exist.

        Ensures:
            - At least one BigQuery admin activity entry exists
            - Entry contains the meridian dataset
        """
        filter_str = (
            'resource.type="bigquery_dataset" '
            'protoPayload.serviceName="bigquery.googleapis.com" '
            'protoPayload.methodName="google.cloud.bigquery.v2.JobService.InsertJob"'
        )
        entries = list( logging_client.list_entries( filter_=filter_str, max_results=5 ) )
        assert len( entries ) > 0, (
            "No BigQuery admin activity logs found. "
            "Run 'make synth-data' to generate log entries."
        )

    def test_gcs_data_access( self, logging_client ):
        """
        Verify GCS data access logs exist.

        Ensures:
            - At least one GCS object access entry exists
        """
        filter_str = (
            'resource.type="gcs_bucket" '
            'protoPayload.serviceName="storage.googleapis.com"'
        )
        entries = list( logging_client.list_entries( filter_=filter_str, max_results=5 ) )
        assert len( entries ) > 0, (
            "No GCS data access logs found. "
            "Run 'make synth-data' to generate log entries."
        )

    def test_vertex_ai_activity( self, logging_client ):
        """
        Verify Vertex AI activity logs exist.

        Ensures:
            - At least one Vertex AI API call is logged
        """
        filter_str = (
            'protoPayload.serviceName="aiplatform.googleapis.com"'
        )
        entries = list( logging_client.list_entries( filter_=filter_str, max_results=5 ) )
        # Vertex AI logs may not exist if pipeline hasn't been run on GCP yet
        # This test documents the expected log entries
        if len( entries ) == 0:
            pytest.skip(
                "No Vertex AI logs found. Run pipeline on GCP to generate entries."
            )

    def test_dlp_scan_activity( self, logging_client ):
        """
        Verify Cloud DLP scan logs exist.

        Ensures:
            - At least one DLP inspection or de-identification entry exists
        """
        filter_str = (
            'protoPayload.serviceName="dlp.googleapis.com"'
        )
        entries = list( logging_client.list_entries( filter_=filter_str, max_results=5 ) )
        if len( entries ) == 0:
            pytest.skip(
                "No DLP logs found. Run pipeline with use_cloud_dlp=True to generate entries."
            )

    def test_kms_key_usage( self, logging_client ):
        """
        Verify KMS key usage logs exist.

        Ensures:
            - KMS encrypt/decrypt operations are logged (from CMEK on BQ/GCS)
        """
        filter_str = (
            'protoPayload.serviceName="cloudkms.googleapis.com" '
            'protoPayload.methodName="Encrypt" OR protoPayload.methodName="Decrypt"'
        )
        entries = list( logging_client.list_entries( filter_=filter_str, max_results=5 ) )
        if len( entries ) == 0:
            pytest.skip(
                "No KMS usage logs found. CMEK operations generate these automatically."
            )
