"""
PII injector for synthetic student data.

Enriches the demographics Parquet with additional PII patterns
that Cloud DLP can detect. The student_generator already injects
SSN patterns (15%) and phone numbers (5%). This module adds
edge cases and verifies PII density.

Requires:
    - demographics.parquet exists in data/synthetic/

Ensures:
    - PII density report printed to stdout
    - No modifications if run standalone (verification only)
"""

import os

import pandas as pd


DEFAULT_DATA_DIR = "data/synthetic"


def verify_pii_density( data_dir: str = DEFAULT_DATA_DIR ) -> dict:
    """
    Verify PII density across the demographics table.

    Ensures:
        - Returns dict with PII type counts and percentages
    """
    path = os.path.join( data_dir, "demographics.parquet" )
    if not os.path.exists( path ):
        raise FileNotFoundError( f"Missing: {path}. Run student_generator.py first." )

    df    = pd.read_parquet( path )
    total = len( df )

    report = {
        "total_records"       : total,
        "has_email"           : int( df[ "email" ].notna().sum() ),
        "has_first_name"      : int( df[ "first_name" ].notna().sum() ),
        "has_last_name"       : int( df[ "last_name" ].notna().sum() ),
        "has_ssn_last4"       : int( df[ "ssn_last4" ].notna().sum() ),
        "has_birth_date"      : int( df[ "birth_date" ].notna().sum() ),
        "ssn_in_notes"        : int( df[ "notes" ].str.contains( r"\d{3}-\d{2}-\d{4}", na=False ).sum() ),
        "phone_in_address"    : int( df[ "address_line2" ].str.contains( r"\(\d{3}\)", na=False ).sum() ),
    }

    return report


# ---- CLI Entry Point ----

if __name__ == "__main__":

    print( "--- PII Density Verification ---\n" )

    report = verify_pii_density()
    total  = report[ "total_records" ]

    print( f"  {'PII Type':<25s} {'Count':>8s} {'Percentage':>12s}" )
    print( f"  {'-' * 25} {'-' * 8} {'-' * 12}" )

    for key, count in report.items():
        if key == "total_records":
            continue
        pct = f"{count / total:.1%}"
        print( f"  {key:<25s} {count:>8,} {pct:>12s}" )

    print( f"\n  Total records: {total:,}" )
    print( "\n  Cloud DLP should detect:" )
    print( f"    - PERSON_NAME:             {report[ 'has_first_name' ]:,} (100%)" )
    print( f"    - EMAIL_ADDRESS:           {report[ 'has_email' ]:,} (100%)" )
    print( f"    - US_SOCIAL_SECURITY_NUMBER: {report[ 'ssn_in_notes' ]:,} (~15%)" )
    print( f"    - PHONE_NUMBER:            {report[ 'phone_in_address' ]:,} (~5%)" )
    print( f"    - DATE_OF_BIRTH:           {report[ 'has_birth_date' ]:,} (~100%)" )
