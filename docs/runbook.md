# Meridian Operational Runbook

## Deployment

### Prerequisites

- GCP project with billing enabled
- Terraform 1.5+
- Python 3.11+
- gcloud CLI (authenticated with `gcloud auth application-default login`)
- Service account with sufficient IAM roles

### Terraform Apply Sequence

Terraform modules must be applied in dependency order:

1. **security** -- KMS keys, service accounts, IAM bindings
2. **storage** -- GCS buckets (pipeline artifacts, model exports, data staging)
3. **networking** -- VPC, subnets, VPC Service Controls, Cloud Armor
4. **bigquery** -- Datasets, tables, authorized views
5. **vertex** -- Vertex AI Pipelines, Feature Store, Model Registry, Endpoints
6. **pubsub** -- Topics and subscriptions (retrain triggers, alerts)
7. **monitoring** -- Dashboards, alert policies, uptime checks
8. **api** -- Cloud Endpoints, Cloud Functions, Memorystore cache

### Quick Deploy

```bash
make deploy
```

### Verify

```bash
terraform plan
# Expected: "No changes. Your infrastructure matches the configuration."
```

---

## Synthetic Data

### Generate and Load

```bash
make synth-data
```

This runs three stages in sequence:

1. `student_generator` -- Creates synthetic student records with Faker
2. `pii_injector` -- Injects realistic PII patterns for DLP testing
3. `load_to_bigquery` -- Loads generated CSVs into BigQuery tables

### Verify

```bash
bq query --project_id=ampe-to-meridian \
  "SELECT COUNT(*) FROM meridian_student_data_dev.student_demographics"
```

### Expected Record Counts

| Table               | Approximate Rows |
|---------------------|------------------|
| student_demographics | 50,000          |
| academic_records     | 200,000         |
| enrollment_events    | 150,000         |
| financial_aid        | 50,000          |

---

## Pipeline Operations

### Run Full Pipeline

```bash
make pipeline
```

### Run Tests

```bash
make test          # All tests (unit + integration)
make test-unit     # Unit tests only
make chaos         # Chaos / resilience tests
```

### Pipeline Stages

The Vertex AI Pipeline consists of 14 KFP v2 components executed in order:

```
ingest -> validate -> dlp_scan -> harmonize -> clean ->
feature_engineer -> feature_store_sync -> reduce_dimensions ->
train -> tune -> evaluate -> explain -> register -> deploy
```

---

## Monitoring

### Dashboards

Three Cloud Monitoring dashboards are provisioned:

| Dashboard              | Purpose                                      |
|------------------------|----------------------------------------------|
| Pipeline Performance   | Stage durations, success/failure rates        |
| Model Health           | Drift scores, prediction distributions        |
| Endpoint Performance   | Latency, throughput, error rates              |

### Alert Thresholds

| Condition                     | Threshold        | Notification     |
|-------------------------------|------------------|------------------|
| Model drift score             | > 0.1            | Email + Pub/Sub  |
| Prediction endpoint 5xx rate  | > 1%             | Immediate page   |
| Pipeline failure              | Any failure      | Immediate page   |

### Check Drift

Navigate to: **Cloud Monitoring -> Custom Metrics -> `meridian/model_drift_score`**

---

## Incident Playbooks

### Model Drift Alert

1. Check the Model Health dashboard for affected features
2. Review recent data changes in BigQuery (schema changes, new data loads)
3. If drift is significant: trigger retrain via Pub/Sub or `make pipeline`
4. If false positive: adjust drift threshold in the monitoring Terraform variables

### Prediction Endpoint Down

1. Check the Endpoint Performance dashboard for error rate spike
2. Verify cache fallback is active (Memorystore should auto-degrade)
3. Check Cloud Run / Vertex Prediction logs in Cloud Logging
4. If persistent: redeploy with `make deploy`

### Pipeline Failure

1. Check pipeline logs in Cloud Logging (filter by pipeline run ID)
2. Common root causes:
   - **Data validation failure** -- TFDV schema mismatch or anomaly detected
   - **DLP threshold exceeded** -- Too many PII findings in input data
   - **Resource quota** -- Exceeded Vertex AI or BigQuery quotas
3. Fix data issues and re-run: `make pipeline`

---

## Cost Management

### Expensive Resources

| Resource                       | Estimated Monthly Cost |
|--------------------------------|------------------------|
| Memorystore (Redis)            | ~$18/mo                |
| Global Load Balancer (GLB)     | ~$18/mo                |
| Feature Store online serving   | ~$5-10/mo              |

### Teardown Commands

```bash
make destroy-expensive   # Tear down Memorystore + GLB only
make destroy             # Full teardown of all resources
```

### Estimated Development Cost

- **Full stack running**: $60-150/mo
- **Expensive resources torn down**: $10-20/mo

---

## Troubleshooting

| Symptom                        | Resolution                                                        |
|--------------------------------|-------------------------------------------------------------------|
| Permission errors              | Check service account roles in the security Terraform module      |
| CMEK errors                    | Verify KMS key access grants for the pipeline service account     |
| Quota limits                   | Request increase via Cloud Console -> IAM & Admin -> Quotas       |
| Feature Store ingestion fails  | Check entity type schema matches feature DataFrame columns        |
| VPC-SC blocking requests       | Check if dry-run mode is enabled (should be `true` for dev)       |
