"""
Secret Manager client wrapper for Meridian pipeline.

Provides a reusable Secret Manager client for retrieving
credentials and API keys without storing them on disk.

Requires:
    - google-cloud-secret-manager installed
    - GCP credentials configured with secretmanager.secretAccessor role

Ensures:
    - Secrets retrieved securely at runtime
    - Local caching to avoid repeated API calls
    - Structured logging (secret values never logged)
"""

from typing import Optional

from utils.logging_config import get_logger

logger = get_logger( __name__ )


class SecretManagerClient:
    """
    Wrapper around google.cloud.secretmanager.SecretManagerServiceClient.

    Requires:
        - project_id is a valid GCP project ID

    Ensures:
        - Lazy initialization of underlying client
        - In-memory cache for retrieved secrets (avoids duplicate API calls)
    """

    def __init__( self, project_id: str ):
        self.project_id = project_id
        self._client    = None
        self._cache     = {}

    @property
    def client( self ):
        """Lazy-initialize the Secret Manager client."""
        if self._client is None:
            from google.cloud import secretmanager
            self._client = secretmanager.SecretManagerServiceClient()
            logger.info( "Secret Manager client initialized" )
        return self._client

    def get_secret( self, secret_id: str, version: str = "latest" ) -> str:
        """
        Retrieve a secret value from Secret Manager.

        Requires:
            - secret_id exists in the project
            - version is a valid version number or "latest"

        Ensures:
            - Returns the secret payload as a UTF-8 string
            - Caches the value to avoid repeated API calls
        """
        cache_key = f"{secret_id}:{version}"
        if cache_key in self._cache:
            logger.info( f"Secret '{secret_id}' retrieved from cache" )
            return self._cache[ cache_key ]

        name    = f"projects/{self.project_id}/secrets/{secret_id}/versions/{version}"
        logger.info( f"Retrieving secret '{secret_id}' (version: {version})" )
        response = self.client.access_secret_version( request={ "name": name } )
        value    = response.payload.data.decode( "UTF-8" )

        self._cache[ cache_key ] = value
        logger.info( f"Secret '{secret_id}' retrieved successfully" )
        return value

    def create_secret( self, secret_id: str, payload: Optional[str] = None ) -> str:
        """
        Create a new secret, optionally with an initial version.

        Requires:
            - secret_id is unique within the project

        Ensures:
            - Returns the secret resource name
            - If payload provided, adds initial version
        """
        parent = f"projects/{self.project_id}"

        logger.info( f"Creating secret '{secret_id}'" )
        secret = self.client.create_secret(
            request={
                "parent"    : parent,
                "secret_id" : secret_id,
                "secret"    : { "replication": { "automatic": {} } },
            }
        )

        if payload is not None:
            self.add_version( secret_id, payload )

        return secret.name

    def add_version( self, secret_id: str, payload: str ) -> str:
        """
        Add a new version to an existing secret.

        Requires:
            - secret_id exists in the project
            - payload is a non-empty string

        Ensures:
            - Returns the version resource name
            - Invalidates cache for this secret
        """
        parent = f"projects/{self.project_id}/secrets/{secret_id}"

        logger.info( f"Adding version to secret '{secret_id}'" )
        version = self.client.add_secret_version(
            request={
                "parent"  : parent,
                "payload" : { "data": payload.encode( "UTF-8" ) },
            }
        )

        # Invalidate cache for this secret
        keys_to_remove = [ k for k in self._cache if k.startswith( f"{secret_id}:" ) ]
        for k in keys_to_remove:
            del self._cache[ k ]

        return version.name
