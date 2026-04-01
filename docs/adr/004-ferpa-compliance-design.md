# ADR 004: FERPA Compliance Design

**Date**: 2026-04-01
**Status**: Accepted
**Context**: Student retention prediction systems handle educational records protected by FERPA (Family Educational Rights and Privacy Act, 20 U.S.C. 1232g). Although Meridian uses synthetic data, the pipeline is designed as if operating on real FERPA-protected records to demonstrate AI-Specific Security and Data Protection competencies.

## Decision

Implement a **defense-in-depth FERPA compliance architecture** using Cloud DLP, VPC Service Controls, Cloud KMS, and Cloud Audit Logs.

## Architecture

### Layer 1: Data Classification (Cloud DLP)
- **Pre-training scan**: Cloud DLP inspects all training data before it enters the pipeline
- **InfoTypes detected**: `PERSON_NAME`, `EMAIL_ADDRESS`, `US_SOCIAL_SECURITY_NUMBER`, `PHONE_NUMBER`, `DATE_OF_BIRTH`
- **Action**: De-identify (replace with surrogate tokens) or block pipeline if PII density exceeds threshold
- **DLP templates**: Stored in Terraform (`infrastructure/modules/security/`) for reproducibility

### Layer 2: Perimeter Security (VPC Service Controls)
- **Service perimeter**: Encompasses Vertex AI, BigQuery, Cloud Storage, Cloud KMS
- **Access levels**: Developer identity allowed; all other egress blocked
- **Mode**: Dry-run during development (Phase 1-4), enforced in Phase 5
- **Purpose**: Prevents data exfiltration from the ML pipeline even if service accounts are compromised

### Layer 3: Encryption (Cloud KMS / CMEK)
- **At rest**: Customer-managed encryption keys (CMEK) on BigQuery dataset and GCS buckets
- **Key rotation**: Automatic 90-day rotation
- **Key ring**: Single key ring per environment (`meridian-dev`, `meridian-staging`)
- **Purpose**: Demonstrates that the organization controls encryption keys, not just Google's default encryption

### Layer 4: Audit Trail (Cloud Audit Logs)
- **Admin Activity logs**: All Terraform changes, IAM modifications (always on, free)
- **Data Access logs**: BigQuery query logs, GCS object access (enabled per-resource)
- **Log sink**: Export to separate BigQuery dataset for retention analysis
- **Purpose**: Demonstrates Compliance & Governance -- who accessed student data, when, and why

### Layer 5: Access Control (IAM + Secret Manager)
- **Principle of least privilege**: Separate service accounts for pipeline, serving, monitoring
- **No long-lived keys**: Workload Identity Federation for CI/CD, no JSON key files
- **Secrets**: Database credentials and API keys in Secret Manager (not environment variables or config files)

## FERPA-Specific Controls

| FERPA Requirement | Meridian Implementation |
|---|---|
| Limit access to educational records | VPC Service Controls + IAM least privilege |
| Maintain audit trail of access | Cloud Audit Logs + Data Access logs to BQ |
| De-identify records for research use | Cloud DLP pre-training scan with surrogate tokenization |
| Encrypt records at rest | CMEK on BigQuery + GCS via Cloud KMS |
| Notify on unauthorized access | Cloud Monitoring alerting on audit log anomalies |

## Consequences

- Cloud DLP scan is a mandatory pipeline component (cannot be skipped)
- VPC Service Controls may initially block development -- dry-run mode mitigates this
- CMEK adds ~$1-3/mo to infrastructure cost
- All security controls are codified in Terraform for reproducibility
