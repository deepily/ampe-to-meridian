# ADR 003: Synthetic Data Strategy

**Date**: 2026-04-01
**Status**: Accepted
**Context**: AMPE operates on real institutional student data from Redshift (demographics, academic records, financial aid, enrollment events). Meridian cannot use real student data (FERPA, no institutional access), so it needs synthetic data that is realistic enough to demonstrate the full pipeline including Cloud DLP PII detection, TFDV data validation, SMOTE class imbalance handling, and meaningful model training.

## Decision

Generate **50,000 synthetic student records** across 4 tables using Python `faker` + `numpy` with correlated distributions and deliberate data quality issues.

## Data Design

### Table 1: `student_demographics` (50,000 rows)
- **PII fields** (for Cloud DLP): `first_name`, `last_name`, `email`, `ssn_last4`
- **Academic**: `hs_gpa` (Normal, mu=3.2, sigma=0.5), `sat_score` (Normal, mu=1050, sigma=200), `act_score`
- **Geographic**: `home_state`, `home_zip`, `campus_latitude`, `campus_longitude`, `campus_distance_miles`
- **Demographic**: `gender`, `ethnicity`, `first_generation_flag`, `birth_date`

### Table 2: `academic_records` (200,000 rows, ~4 per student)
- `term` (Fall 2019 through Spring 2022), `term_gpa`, `cumulative_gpa`
- `credits_attempted`, `credits_earned`, `course_count`, `major`, `academic_standing`

### Table 3: `financial_aid` (50,000 rows)
- `efc` (expected family contribution), `pell_eligible`, `total_aid_amount`
- `loan_amount`, `grant_amount`, `scholarship_amount`, `unmet_need`, `work_study_flag`

### Table 4: `enrollment_events` (150,000 rows, ~3 per student)
- `event_type` (application, acceptance, enrollment, withdrawal, graduation)
- `event_date`, `enrollment_status`, **`second_year_ret_flag`** (target variable)

### Correlation Structure
- GPA <-> retention: r ~= 0.4 (positive)
- Financial need <-> retention: r ~= -0.25 (negative)
- First-generation <-> retention: r ~= -0.15 (slight negative)
- SAT score <-> GPA: r ~= 0.5 (positive)
- Class imbalance: 75% retained / 25% not retained

### PII Injection for Cloud DLP
- 100% have `first_name`, `last_name`, `email` (standard PII)
- 15% have SSN-like patterns (`###-##-####`) in a `notes` text field
- 5% have phone numbers in `address_line2`
- Purpose: give Cloud DLP meaningful detection work beyond trivial name matching

### Deliberate Data Quality Issues for TFDV
- 2% null `hs_gpa` values (missing data)
- 1% out-of-range `sat_score` > 1600 or < 0 (anomaly)
- 0.5% future `event_date` values (temporal anomaly)
- Purpose: TFDV schema validation catches these, demonstrating Failure & Recovery Testing

## Consequences

- Data is generated locally as Parquet, uploaded to GCS, loaded into BigQuery
- CSV copies in GCS for TFDV schema generation
- Reproducible via fixed random seed (`numpy.random.seed(42)`)
- Schema JSON files in `src/data_synthesis/schemas/` mirror BigQuery table definitions
