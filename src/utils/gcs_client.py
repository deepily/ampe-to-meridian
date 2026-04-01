"""
Google Cloud Storage client wrapper for Meridian pipeline.

Provides a reusable GCS client with consistent error handling
and structured logging. Replaces inline client instantiation.

Requires:
    - google-cloud-storage installed
    - GCP credentials configured

Ensures:
    - Single client instance per wrapper
    - CMEK-aware operations (bucket-level encryption)
    - Structured logging for all operations
"""

import os
from typing import List, Optional

from utils.logging_config import get_logger

logger = get_logger( __name__, component="gcs_client" )


class GCSClient:
    """
    Wrapper around google.cloud.storage.Client.

    Requires:
        - bucket_name is a valid GCS bucket name

    Ensures:
        - Lazy initialization of underlying client
        - All operations logged with structured output
    """

    def __init__( self, bucket_name: str ):
        self.bucket_name = bucket_name
        self._client     = None
        self._bucket     = None

    @property
    def client( self ):
        """Lazy-initialize the GCS client."""
        if self._client is None:
            from google.cloud import storage
            self._client = storage.Client()
            logger.info( f"GCS client initialized" )
        return self._client

    @property
    def bucket( self ):
        """Lazy-initialize the bucket reference."""
        if self._bucket is None:
            self._bucket = self.client.bucket( self.bucket_name )
        return self._bucket

    def upload_file( self, local_path: str, blob_path: str ) -> str:
        """
        Upload a local file to GCS.

        Requires:
            - local_path exists and is readable
            - blob_path is the destination path within the bucket

        Ensures:
            - Returns the GCS URI: gs://bucket/blob_path
        """
        blob = self.bucket.blob( blob_path )
        logger.info( f"Uploading {local_path} -> gs://{self.bucket_name}/{blob_path}" )
        blob.upload_from_filename( local_path )
        uri = f"gs://{self.bucket_name}/{blob_path}"
        logger.info( f"  Upload complete: {uri}" )
        return uri

    def download_file( self, blob_path: str, local_path: str ) -> str:
        """
        Download a file from GCS to local disk.

        Requires:
            - blob_path exists in the bucket
            - local_path parent directory exists or will be created

        Ensures:
            - Returns the local file path
        """
        os.makedirs( os.path.dirname( local_path ) or ".", exist_ok=True )
        blob = self.bucket.blob( blob_path )
        logger.info( f"Downloading gs://{self.bucket_name}/{blob_path} -> {local_path}" )
        blob.download_to_filename( local_path )
        return local_path

    def list_blobs( self, prefix: Optional[str] = None ) -> List[str]:
        """
        List blob names in the bucket with optional prefix filter.

        Requires:
            - prefix is a string path prefix or None for all blobs

        Ensures:
            - Returns a list of blob name strings
        """
        blobs = self.client.list_blobs( self.bucket_name, prefix=prefix )
        names = [ blob.name for blob in blobs ]
        logger.info( f"Listed {len( names )} blobs in gs://{self.bucket_name}/{prefix or ''}" )
        return names

    def upload_directory( self, local_dir: str, prefix: str ) -> List[str]:
        """
        Upload all files in a directory to GCS.

        Requires:
            - local_dir is a valid directory path
            - prefix is the GCS path prefix

        Ensures:
            - Returns list of GCS URIs for uploaded files
        """
        uris = []
        for filename in os.listdir( local_dir ):
            local_path = os.path.join( local_dir, filename )
            if os.path.isfile( local_path ):
                blob_path = f"{prefix}/{filename}"
                uri       = self.upload_file( local_path, blob_path )
                uris.append( uri )
        return uris
