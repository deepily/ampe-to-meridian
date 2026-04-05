"""
Shared filesystem + Parquet I/O helpers for Meridian pipeline components.

Centralizes the mkdir-before-write and parquet read/write boilerplate that
previously appeared inline in every component.

Requires:
    - pandas, pyarrow installed

Ensures:
    - ensure_parent_dir is idempotent and no-ops when parent is the cwd
    - write_parquet creates parent dirs before writing
"""

import os

import pandas as pd


def ensure_parent_dir( path: str ) -> None:
    """
    Ensure the parent directory of `path` exists.

    Requires:
        - path is a non-empty string

    Ensures:
        - os.path.dirname( path ) exists as a directory after the call
        - no-op if parent is "" (path is in current directory)
    """
    os.makedirs( os.path.dirname( path ) or ".", exist_ok=True )


def read_parquet( path: str ) -> pd.DataFrame:
    """Read a Parquet file as a DataFrame."""
    return pd.read_parquet( path )


def write_parquet( df: pd.DataFrame, path: str ) -> None:
    """
    Write a DataFrame to Parquet, creating parent directories as needed.

    Requires:
        - df is a pandas DataFrame
        - path is a writable filesystem path

    Ensures:
        - Parent directory of path exists
        - Parquet written with index=False
    """
    ensure_parent_dir( path )
    df.to_parquet( path, index=False )
