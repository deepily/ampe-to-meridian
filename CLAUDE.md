# Meridian: GCP-Native Student Retention ML Pipeline

## Project Overview

Meridian is a GCP-native reimplementation of the AMPE (Abstracted Modeling and Prediction Engine) framework. It replaces AMPE's artisanal AWS-centric ML pipeline with managed GCP services for student retention prediction.

**Domain**: Higher education student retention/persistence prediction
**Original**: `/mnt/DATA01/include/www.deepily.ai/projects/ampe`
**Parent repo**: `/mnt/DATA01/include/www.deepily.ai/projects/google/fde-prep`

## Key References

- **Plan**: `rnd/2026.04.01-meridian-gcp-replacement-plan.md`
- **Tracker**: `rnd/2026.04.01-meridian-implementation-tracker.md`
- **Gap analysis**: `../rnd/2026.03.31-fde-competency-product-gap-analysis.md`
- **AMPE source**: `/mnt/DATA01/include/www.deepily.ai/projects/ampe/`

## Architecture

Pipeline stages (KFP v2 components):
ingest -> validate (TFDV) -> dlp_scan -> harmonize -> clean -> feature_engineer -> feature_store_sync -> reduce_dimensions -> train -> tune -> evaluate -> explain -> register -> deploy

## GCP Products Used

Vertex AI (Pipelines, Experiments, Feature Store, Model Registry, Model Monitoring, TensorBoard, Vizier, Explainable AI, Prediction), BigQuery, Cloud Storage, Cloud KMS, Secret Manager, Cloud DLP, VPC Service Controls, Cloud Monitoring, Cloud Logging, Cloud Trace, Cloud Armor, Memorystore, Cloud Endpoints, Cloud Functions, Pub/Sub, Cloud Build, Cloud Audit Logs

## Development

```bash
make synth-data    # Generate + load synthetic student data
make pipeline      # Run Vertex AI Pipeline end-to-end
make test          # Run unit + integration tests
make chaos         # Run chaos tests
make deploy        # Deploy Terraform + pipeline
make destroy       # Tear down all resources
make destroy-expensive  # Tear down Memorystore + GLB only
```

## Project Prefix

Use `[MERIDIAN]` for all TODO items and tracking.
