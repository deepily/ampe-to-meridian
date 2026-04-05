"""
BigQuery client wrapper for Meridian pipeline.

Provides a reusable BigQuery client with consistent error handling
and structured logging. Replaces inline client instantiation.

Requires:
    - google-cloud-bigquery installed
    - GCP credentials configured

Ensures:
    - Single client instance per wrapper
    - Structured logging for all operations
    - Consistent error handling patterns
"""

from typing import Optional

import pandas as pd

from utils.logging_config import get_logger

logger = get_logger( __name__ )


class BigQueryClient:
    """
    Wrapper around google.cloud.bigquery.Client.

    Requires:
        - project_id is a valid GCP project ID

    Ensures:
        - Lazy initialization of underlying client
        - All operations logged with structured output
    """

    def __init__( self, project_id: str ):
        self.project_id = project_id
        self._client    = None

    @property
    def client( self ):
        """Lazy-initialize the BigQuery client."""
        if self._client is None:
            from google.cloud import bigquery
            self._client = bigquery.Client( project=self.project_id )
            logger.info( f"BigQuery client initialized for project: {self.project_id}" )
        return self._client

    def list_rows( self, table_id: str ) -> pd.DataFrame:
        """
        Read all rows from a BigQuery table into a DataFrame.

        Requires:
            - table_id is fully qualified: project.dataset.table

        Ensures:
            - Returns a pandas DataFrame with all rows
            - DATE columns converted to pandas datetime64 (avoids db-dtypes
              extension type that breaks parquet round-trips between KFP tasks)
        """
        logger.info( f"Reading rows from {table_id}" )
        df = self.client.list_rows( table_id ).to_dataframe()
        # Coerce db-dtypes DATE/TIME extension types to plain datetime to keep
        # parquet files portable across pipeline tasks.
        for col in df.columns:
            dtype_name = str( df[ col ].dtype )
            if dtype_name in ( "dbdate", "dbtime" ):
                df[ col ] = pd.to_datetime( df[ col ], errors="coerce" )
        logger.info( f"  Read {len( df ):,} rows from {table_id}" )
        return df

    def load_from_dataframe(
        self,
        df        : pd.DataFrame,
        table_id  : str,
        write_mode: str = "WRITE_TRUNCATE",
    ) -> int:
        """
        Load a DataFrame into a BigQuery table.

        Requires:
            - df is a non-empty DataFrame
            - table_id is fully qualified: project.dataset.table
            - write_mode is WRITE_TRUNCATE, WRITE_APPEND, or WRITE_EMPTY

        Ensures:
            - Returns the number of rows in the table after load
        """
        from google.cloud import bigquery

        job_config = bigquery.LoadJobConfig(
            write_disposition = getattr( bigquery.WriteDisposition, write_mode ),
            source_format     = bigquery.SourceFormat.PARQUET,
        )

        logger.info( f"Loading {len( df ):,} rows -> {table_id}" )
        job = self.client.load_table_from_dataframe( df, table_id, job_config=job_config )
        job.result()

        table     = self.client.get_table( table_id )
        row_count = table.num_rows
        logger.info( f"  Verified: {row_count:,} rows in {table_id}" )
        return row_count

    def query( self, sql: str ) -> pd.DataFrame:
        """
        Execute a SQL query and return results as a DataFrame.

        Requires:
            - sql is a valid BigQuery SQL string

        Ensures:
            - Returns a pandas DataFrame with query results
        """
        logger.info( f"Executing query: {sql[:100]}..." )
        df = self.client.query( sql ).to_dataframe()
        logger.info( f"  Query returned {len( df ):,} rows" )
        return df

    def get_table( self, table_id: str ):
        """
        Get table metadata.

        Requires:
            - table_id is fully qualified: project.dataset.table

        Ensures:
            - Returns a google.cloud.bigquery.Table object
        """
        return self.client.get_table( table_id )
