# ADR 002: BigQuery over Cloud SQL for Data Warehouse

**Date**: 2026-04-01
**Status**: Accepted
**Context**: AMPE uses Amazon Redshift as its data warehouse. Meridian needs a GCP equivalent for storing student demographics, academic records, financial aid, and enrollment events (~450K total rows across 4 tables).

## Decision

Use **BigQuery** as the primary data warehouse, replacing Redshift.

## Rationale

| Factor | BigQuery | Cloud SQL (PostgreSQL) |
|--------|---------|----------------------:|
| Redshift equivalent | Yes -- columnar, serverless, SQL analytics | No -- OLTP, row-oriented |
| AMPE column compatibility | SQL dialect differences are minor (BQ Standard SQL) | PostgreSQL is closest to Redshift dialect |
| Partitioning | Native partition by `enrollment_term` | Manual partitioning via table inheritance |
| CMEK encryption | Built-in, per-dataset | Built-in, per-instance |
| Cost at 450K rows | Free tier (10 GB storage, 1 TB queries/mo) | ~$7-15/mo for smallest instance |
| Vertex AI integration | Native: BQ as pipeline source, Feature Store sync, BQML | Requires custom connectors |
| FDE competency alignment | Demonstrates Resource Efficiency (partitioning, clustering) | Less relevant to gap competencies |

## Trade-offs

- Cloud SQL PostgreSQL would be a closer 1:1 Redshift replacement (same SQL dialect)
- BigQuery is serverless and free at this scale, making it more cost-effective for development
- BigQuery's native Vertex AI integration simplifies the pipeline (ingest component reads directly from BQ)

## Consequences

- 4 BigQuery tables in a single dataset (`meridian_student_data`)
- Partitioned by `enrollment_term` (RANGE or INGESTION_TIME)
- Clustered by `campus`, `cohort_year` for common query patterns
- CMEK encryption via Cloud KMS key
- Data synthesis loads directly into BQ via `google-cloud-bigquery` client
