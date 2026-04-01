# ADR 001: Vertex AI Pipelines over Cloud Composer

**Date**: 2026-04-01
**Status**: Accepted
**Context**: Meridian needs an orchestration layer for its 14-component ML pipeline. Two GCP options exist: Cloud Composer (managed Apache Airflow) and Vertex AI Pipelines (managed Kubeflow Pipelines).

## Decision

Use **Vertex AI Pipelines** (KFP v2 DSL) as the pipeline orchestrator.

## Rationale

| Factor | Vertex AI Pipelines | Cloud Composer |
|--------|--------------------:|---------------:|
| ML-native | Yes -- built for ML workflows, artifact tracking, experiment integration | No -- general-purpose DAG scheduler, ML is bolted on |
| Managed infra | Serverless, pay-per-run | Always-on Airflow environment (~$300-400/mo minimum) |
| Vertex AI integration | Native: Experiments, Model Registry, Feature Store, TensorBoard | Requires custom operators for each Vertex service |
| Pipeline artifacts | First-class KFP Artifacts with ML Metadata lineage | Airflow XComs -- no lineage tracking |
| Cost (dev) | $5-15/mo for ~20 runs | $300-400/mo for smallest environment |
| Learning curve | KFP v2 lightweight Python components | Airflow DAGs, operators, sensors, connections |
| FDE competency alignment | Directly demonstrates AI Lifecycle Management (CRITICAL weak) | Demonstrates orchestration but not ML lifecycle governance |

## Trade-offs

- Cloud Composer is better for complex cross-system orchestration (ETL, multi-service DAGs)
- Vertex AI Pipelines is purpose-built for ML and aligns with FDE competency requirements
- The existing lupin Vertex AI Pipeline design doc provides reusable KFP v2 patterns

## Consequences

- Pipeline defined in `src/pipeline/vertex_pipeline.py` using `kfp.v2.dsl`
- Each stage is a lightweight Python component (no containerized components unless needed)
- Pipeline runs are tracked in Vertex AI Experiments automatically
- ML Metadata captures lineage from training data through to deployed model
