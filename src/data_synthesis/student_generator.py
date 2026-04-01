"""
Synthetic student data generator for Meridian ML pipeline.

Generates 50,000 realistic student records across 4 tables
with correlated distributions, PII fields for Cloud DLP,
and deliberate data quality issues for TFDV validation.

Requires:
    - faker, numpy, pandas installed
    - Called as module: python -m src.data_synthesis.student_generator

Ensures:
    - 4 Parquet files written to output_dir
    - Correlated distributions: GPA <-> retention (r ~= 0.4)
    - Class imbalance: 75% retained / 25% not retained
    - 2-3% deliberate data quality issues for TFDV

Raises:
    - RuntimeError if output directory cannot be created
"""

import os
import uuid
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from faker import Faker

# ---- Constants ----

NUM_STUDENTS                = 50_000
RECORDS_PER_STUDENT_ACADEMIC = 4
RECORDS_PER_STUDENT_EVENTS   = 3
RETENTION_RATE              = 0.75
RANDOM_SEED                 = 42
DEFAULT_OUTPUT_DIR          = "data/synthetic"

CAMPUSES = [
    ( "Main Campus",         38.4493, -78.8689 ),
    ( "Downtown Center",     38.4370, -78.8700 ),
    ( "Online",              0.0,      0.0 ),
    ( "Satellite North",     38.9200, -77.0370 ),
    ( "Satellite South",     37.5400, -77.4360 ),
]

MAJORS = [
    "Computer Science", "Biology", "Business Administration", "Psychology",
    "Nursing", "English", "Mathematics", "History", "Chemistry", "Education",
    "Political Science", "Engineering", "Communications", "Sociology",
    "Economics", "Art", "Music", "Philosophy", "Undeclared",
]

ETHNICITIES = [
    "White", "Black/African American", "Hispanic/Latino",
    "Asian", "Two or More Races", "Unknown", "Native American",
    "Pacific Islander",
]

TERMS = [
    ( "Fall 2019",   201900 ),
    ( "Spring 2020", 202000 ),
    ( "Fall 2020",   202010 ),
    ( "Spring 2021", 202100 ),
    ( "Fall 2021",   202110 ),
    ( "Spring 2022", 202200 ),
]

EVENT_TYPES = ["application", "acceptance", "enrollment", "withdrawal", "graduation"]

US_STATES = [
    "VA", "MD", "PA", "NC", "WV", "DC", "NY", "NJ", "DE", "OH",
    "CA", "TX", "FL", "GA", "IL", "MA", "CT", "SC", "TN", "KY",
]


class StudentDataGenerator:
    """
    Generates correlated synthetic student data for the Meridian pipeline.

    Requires:
        - num_students > 0
        - 0 < retention_rate < 1
        - random_seed is a non-negative integer

    Ensures:
        - All DataFrames have student_id as a common key
        - Demographics has exactly num_students rows
        - Academic records has ~num_students * records_per_student rows
        - Retention flag distribution matches retention_rate +/- 2%
    """

    def __init__(
        self,
        num_students   : int = NUM_STUDENTS,
        retention_rate : float = RETENTION_RATE,
        random_seed    : int = RANDOM_SEED,
        output_dir     : str = DEFAULT_OUTPUT_DIR,
    ):
        self.num_students   = num_students
        self.retention_rate = retention_rate
        self.random_seed    = random_seed
        self.output_dir     = output_dir

        np.random.seed( self.random_seed )
        self.fake = Faker()
        Faker.seed( self.random_seed )

    def generate_all( self ) -> dict:
        """
        Generate all 4 tables and return as dict of DataFrames.

        Ensures:
            - Returns dict with keys: demographics, academic_records, financial_aid, enrollment_events
            - All DataFrames are non-empty
        """
        print( "Generating student demographics..." )
        demographics = self._generate_demographics()

        print( "Generating academic records..." )
        academic = self._generate_academic_records( demographics )

        print( "Generating financial aid..." )
        financial = self._generate_financial_aid( demographics )

        print( "Generating enrollment events..." )
        events = self._generate_enrollment_events( demographics )

        return {
            "demographics"     : demographics,
            "academic_records" : academic,
            "financial_aid"    : financial,
            "enrollment_events": events,
        }

    def save_all( self, tables: Optional[dict] = None ) -> dict:
        """
        Generate (if needed) and save all tables to Parquet.

        Ensures:
            - Creates output_dir if it doesn't exist
            - Writes 4 .parquet files
            - Returns dict of file paths
        """
        if tables is None:
            tables = self.generate_all()

        os.makedirs( self.output_dir, exist_ok=True )

        paths = {}
        for name, df in tables.items():
            path = os.path.join( self.output_dir, f"{name}.parquet" )
            df.to_parquet( path, index=False )
            paths[ name ] = path
            print( f"  Saved {name}: {len( df ):,} rows -> {path}" )

        # Also save as CSV for TFDV schema generation
        for name, df in tables.items():
            csv_path = os.path.join( self.output_dir, f"{name}.csv" )
            df.to_csv( csv_path, index=False )

        return paths

    # ---- Demographics ----

    def _generate_demographics( self ) -> pd.DataFrame:
        """Generate 50K student demographics with PII and correlated features."""

        # Generate base latent variable that drives retention
        # This creates correlations between GPA, finances, and retention
        latent = np.random.normal( 0, 1, self.num_students )

        # GPA correlated with latent (r ~= 0.5)
        hs_gpa_raw = 3.2 + 0.5 * latent + np.random.normal( 0, 0.3, self.num_students )
        hs_gpa     = np.clip( hs_gpa_raw, 0.0, 4.0 )

        # SAT correlated with GPA (r ~= 0.5)
        sat_raw = 1050 + 100 * latent + np.random.normal( 0, 150, self.num_students )
        sat     = np.clip( sat_raw, 400, 1600 ).astype( int )

        # ACT correlated with SAT
        act_raw = 21 + 3 * latent + np.random.normal( 0, 3, self.num_students )
        act     = np.clip( act_raw, 1, 36 ).astype( int )

        # First generation flag (anti-correlated with latent)
        first_gen_prob = 1.0 / ( 1.0 + np.exp( 0.5 * latent ) )
        first_gen      = np.random.binomial( 1, first_gen_prob ).astype( bool )

        # Campus assignment
        campus_indices = np.random.choice( len( CAMPUSES ), self.num_students, p=[0.45, 0.15, 0.20, 0.10, 0.10] )

        # Generate PII
        student_ids = [str( uuid.uuid4() )[:12] for _ in range( self.num_students )]
        first_names = [self.fake.first_name() for _ in range( self.num_students )]
        last_names  = [self.fake.last_name() for _ in range( self.num_students )]
        emails      = [f"{fn.lower()}.{ln.lower()}@university.edu" for fn, ln in zip( first_names, last_names )]

        # SSN last 4 (nullable -- some have it, some don't)
        ssn_last4 = [
            f"{np.random.randint( 1000, 9999 )}" if np.random.random() < 0.7 else None
            for _ in range( self.num_students )
        ]

        # Birth dates (18-25 years old relative to Fall 2019)
        birth_dates = [
            date( 2001, 1, 1 ) - timedelta( days=int( np.random.uniform( 0, 365 * 7 ) ) )
            for _ in range( self.num_students )
        ]

        df = pd.DataFrame( {
            "student_id"            : student_ids,
            "first_name"            : first_names,
            "last_name"             : last_names,
            "email"                 : emails,
            "ssn_last4"             : ssn_last4,
            "birth_date"            : birth_dates,
            "gender"                : np.random.choice( ["Male", "Female", "Non-binary", "Prefer not to say"], self.num_students, p=[0.45, 0.47, 0.05, 0.03] ),
            "ethnicity"             : np.random.choice( ETHNICITIES, self.num_students, p=[0.50, 0.15, 0.12, 0.08, 0.06, 0.04, 0.03, 0.02] ),
            "first_generation_flag" : first_gen,
            "hs_gpa"                : np.round( hs_gpa, 2 ),
            "sat_score"             : sat,
            "act_score"             : act,
            "home_state"            : np.random.choice( US_STATES, self.num_students, p=[0.25, 0.10, 0.08, 0.07, 0.05, 0.05, 0.05, 0.05, 0.03, 0.03, 0.03, 0.03, 0.03, 0.02, 0.02, 0.02, 0.02, 0.02, 0.02, 0.03] ),
            "home_zip"              : [self.fake.zipcode() for _ in range( self.num_students )],
            "campus"                : [CAMPUSES[ i ][ 0 ] for i in campus_indices],
            "campus_latitude"       : [CAMPUSES[ i ][ 1 ] for i in campus_indices],
            "campus_longitude"      : [CAMPUSES[ i ][ 2 ] for i in campus_indices],
            "campus_distance_miles" : np.round( np.abs( np.random.normal( 50, 80, self.num_students ) ), 1 ),
            "hs_latitude"           : np.round( 38.0 + np.random.uniform( -3, 3, self.num_students ), 4 ),
            "hs_longitude"          : np.round( -78.0 + np.random.uniform( -3, 3, self.num_students ), 4 ),
            "cohort_year"           : np.random.choice( [2019, 2020, 2021], self.num_students, p=[0.40, 0.35, 0.25] ),
            "notes"                 : [None] * self.num_students,
            "address_line2"         : [None] * self.num_students,
        } )

        # Store latent for use by other generators
        df[ "_latent" ] = latent

        # Inject PII into notes field (15% have SSN-like patterns)
        pii_mask = np.random.random( self.num_students ) < 0.15
        for idx in np.where( pii_mask )[ 0 ]:
            ssn = f"{np.random.randint( 100, 999 )}-{np.random.randint( 10, 99 )}-{np.random.randint( 1000, 9999 )}"
            df.loc[ idx, "notes" ] = f"Student SSN for verification: {ssn}"

        # Inject phone numbers into address_line2 (5%)
        phone_mask = np.random.random( self.num_students ) < 0.05
        for idx in np.where( phone_mask )[ 0 ]:
            phone = f"({np.random.randint( 200, 999 )}) {np.random.randint( 200, 999 )}-{np.random.randint( 1000, 9999 )}"
            df.loc[ idx, "address_line2" ] = f"Contact: {phone}"

        # ---- Deliberate data quality issues for TFDV ----

        # 2% null hs_gpa
        null_gpa_mask = np.random.random( self.num_students ) < 0.02
        df.loc[ null_gpa_mask, "hs_gpa" ] = None

        # 1% out-of-range SAT scores
        bad_sat_mask = np.random.random( self.num_students ) < 0.01
        df.loc[ bad_sat_mask, "sat_score" ] = np.random.choice( [-100, 2000, 9999], size=bad_sat_mask.sum() )

        return df

    # ---- Academic Records ----

    def _generate_academic_records( self, demographics: pd.DataFrame ) -> pd.DataFrame:
        """Generate ~200K academic records (4 per student) correlated with demographics."""

        records = []
        for _, student in demographics.iterrows():
            latent     = student[ "_latent" ]
            student_id = student[ "student_id" ]
            cohort     = student[ "cohort_year" ]

            # Number of terms (2-6, correlated with retention)
            num_terms = min( 6, max( 2, int( 3 + latent + np.random.normal( 0, 0.5 ) ) ) )

            # Filter to terms after cohort
            available_terms = [( t, c ) for t, c in TERMS if c >= cohort * 100][ :num_terms ]

            cumulative_gpa = 0.0
            for i, ( term_name, term_code ) in enumerate( available_terms ):
                base_gpa    = 2.8 + 0.3 * latent + np.random.normal( 0, 0.4 )
                term_gpa    = round( np.clip( base_gpa, 0.0, 4.0 ), 2 )
                cumulative_gpa = round( ( cumulative_gpa * i + term_gpa ) / ( i + 1 ), 2 ) if i > 0 else term_gpa

                credits_attempted = int( np.clip( np.random.normal( 15, 3 ), 6, 21 ) )
                credits_earned    = int( np.clip( credits_attempted - np.random.poisson( 1 ), 0, credits_attempted ) )

                campus = student[ "campus" ]
                major  = np.random.choice( MAJORS ) if i == 0 else records[ -1 ][ "major" ]

                # 10% chance of major change per term
                major_changed = False
                if i > 0 and np.random.random() < 0.10:
                    major         = np.random.choice( MAJORS )
                    major_changed = True

                standing = "good"
                if cumulative_gpa < 1.5: standing = "suspension"
                elif cumulative_gpa < 2.0: standing = "probation"

                records.append( {
                    "student_id"         : student_id,
                    "term"               : term_name,
                    "term_code"          : term_code,
                    "term_gpa"           : term_gpa,
                    "cumulative_gpa"     : cumulative_gpa,
                    "credits_attempted"  : credits_attempted,
                    "credits_earned"     : credits_earned,
                    "course_count"       : int( np.clip( np.random.normal( 5, 1 ), 2, 8 ) ),
                    "major"              : major,
                    "major_changed_flag" : major_changed,
                    "academic_standing"  : standing,
                    "campus"             : campus,
                } )

        return pd.DataFrame( records )

    # ---- Financial Aid ----

    def _generate_financial_aid( self, demographics: pd.DataFrame ) -> pd.DataFrame:
        """Generate 50K financial aid records anti-correlated with retention."""

        latent = demographics[ "_latent" ].values

        # EFC anti-correlated with latent (lower income -> lower latent -> lower retention)
        efc_raw = 15000 - 5000 * latent + np.random.normal( 0, 8000, self.num_students )
        efc     = np.clip( efc_raw, 0, 99999 ).round( 2 )

        pell_eligible = efc < 6000

        total_aid     = np.clip( 25000 - efc * 0.5 + np.random.normal( 0, 5000, self.num_students ), 0, 50000 ).round( 2 )
        loan_pct      = np.clip( np.random.normal( 0.4, 0.15, self.num_students ), 0, 0.8 )
        grant_pct     = np.clip( np.random.normal( 0.35, 0.15, self.num_students ), 0, 0.6 )
        scholarship_pct = np.clip( 1.0 - loan_pct - grant_pct, 0, 0.5 )

        loan_amount       = ( total_aid * loan_pct ).round( 2 )
        grant_amount      = ( total_aid * grant_pct ).round( 2 )
        scholarship_amount = ( total_aid * scholarship_pct ).round( 2 )
        unmet_need        = np.clip( efc - total_aid + np.random.normal( 0, 3000, self.num_students ), 0, 30000 ).round( 2 )

        # FAFSA filing dates (most file Jan-Mar)
        fafsa_dates = [
            date( 2019, 1, 1 ) + timedelta( days=int( np.random.uniform( 0, 120 ) ) )
            for _ in range( self.num_students )
        ]

        return pd.DataFrame( {
            "student_id"         : demographics[ "student_id" ].values,
            "fafsa_filed_date"   : fafsa_dates,
            "efc"                : efc,
            "pell_eligible"      : pell_eligible,
            "total_aid_amount"   : total_aid,
            "loan_amount"        : loan_amount,
            "grant_amount"       : grant_amount,
            "scholarship_amount" : scholarship_amount,
            "unmet_need"         : unmet_need,
            "work_study_flag"    : np.random.random( self.num_students ) < 0.15,
        } )

    # ---- Enrollment Events ----

    def _generate_enrollment_events( self, demographics: pd.DataFrame ) -> pd.DataFrame:
        """Generate ~150K enrollment events with retention target variable."""

        events = []
        for _, student in demographics.iterrows():
            student_id = student[ "student_id" ]
            latent     = student[ "_latent" ]
            cohort     = student[ "cohort_year" ]

            # Retention probability driven by latent variable
            # Logistic function: P(retain) = sigmoid( 0.8 * latent + 1.1 )
            # Bias of 1.1 (ln(3)) shifts median retention to ~75%
            retain_prob = 1.0 / ( 1.0 + np.exp( -( 0.8 * latent + 1.1 ) ) )
            retained    = int( np.random.random() < retain_prob )

            # Application event
            app_date = date( cohort - 1, 10, 1 ) + timedelta( days=int( np.random.uniform( 0, 180 ) ) )
            events.append( {
                "student_id"           : student_id,
                "event_type"           : "application",
                "event_date"           : app_date,
                "term"                 : f"Fall {cohort}",
                "enrollment_status"    : None,
                "second_year_ret_flag" : None,
            } )

            # Acceptance event
            accept_date = app_date + timedelta( days=int( np.random.uniform( 30, 90 ) ) )
            events.append( {
                "student_id"           : student_id,
                "event_type"           : "acceptance",
                "event_date"           : accept_date,
                "term"                 : f"Fall {cohort}",
                "enrollment_status"    : None,
                "second_year_ret_flag" : None,
            } )

            # Enrollment event (with retention flag)
            enroll_date = date( cohort, 8, 15 ) + timedelta( days=int( np.random.uniform( 0, 30 ) ) )
            status      = np.random.choice( ["full-time", "part-time"], p=[0.82, 0.18] )
            events.append( {
                "student_id"           : student_id,
                "event_type"           : "enrollment",
                "event_date"           : enroll_date,
                "term"                 : f"Fall {cohort}",
                "enrollment_status"    : status,
                "second_year_ret_flag" : retained,
            } )

            # If not retained, add withdrawal event
            if not retained and np.random.random() < 0.7:
                withdraw_date = date( cohort + 1, 1, 1 ) + timedelta( days=int( np.random.uniform( 0, 180 ) ) )
                events.append( {
                    "student_id"           : student_id,
                    "event_type"           : "withdrawal",
                    "event_date"           : withdraw_date,
                    "term"                 : f"Spring {cohort + 1}",
                    "enrollment_status"    : "not_enrolled",
                    "second_year_ret_flag" : 0,
                } )

        df = pd.DataFrame( events )

        # ---- Deliberate data quality issue: 0.5% future dates ----
        future_mask = np.random.random( len( df ) ) < 0.005
        df.loc[ future_mask, "event_date" ] = date( 2027, 6, 15 )

        return df


# ---- CLI Entry Point ----

if __name__ == "__main__":

    generator = StudentDataGenerator()
    tables    = generator.generate_all()
    paths     = generator.save_all( tables )

    # Print summary
    print( "\n--- Synthetic Data Summary ---" )
    for name, df in tables.items():
        print( f"  {name:25s}: {len( df ):>8,} rows, {len( df.columns ):>3} columns" )

    # Verify retention rate
    events    = tables[ "enrollment_events" ]
    enrolled  = events[ events[ "event_type" ] == "enrollment" ]
    ret_rate  = enrolled[ "second_year_ret_flag" ].mean()
    print( f"\n  Retention rate: {ret_rate:.1%} (target: {RETENTION_RATE:.0%})" )

    # Verify PII injection
    demo      = tables[ "demographics" ]
    ssn_notes = demo[ "notes" ].notna().sum()
    phone_addr = demo[ "address_line2" ].notna().sum()
    print( f"  PII in notes: {ssn_notes:,} ({ssn_notes/len( demo ):.1%})" )
    print( f"  PII in address_line2: {phone_addr:,} ({phone_addr/len( demo ):.1%})" )

    # Verify data quality issues
    null_gpa = demo[ "hs_gpa" ].isna().sum()
    bad_sat  = ( ( demo[ "sat_score" ] < 400 ) | ( demo[ "sat_score" ] > 1600 ) ).sum()
    print( f"  Null hs_gpa: {null_gpa:,} ({null_gpa/len( demo ):.1%})" )
    print( f"  Out-of-range SAT: {bad_sat:,} ({bad_sat/len( demo ):.1%})" )

    # Drop internal latent column before saving
    demo_clean = demo.drop( columns=["_latent"] )
    tables[ "demographics" ] = demo_clean
    generator.save_all( tables )
