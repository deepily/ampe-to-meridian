# Meridian System Architecture

Meridian is a GCP-native reimplementation of the AMPE (Abstracted Modeling and Prediction Engine) framework. It replaces AMPE's artisanal AWS-centric ML pipeline with managed GCP services for student retention/persistence prediction. The system covers 15 FDE competencies across 23+ GCP products.

---

## Pipeline DAG

The core ML pipeline consists of 14 KFP v2 components executed on Vertex AI Pipelines.

```mermaid
flowchart LR
    ingest["ingest"]
    validate["validate<br/>(TFDV)"]
    dlp_scan["dlp_scan"]
    harmonize["harmonize"]
    clean["clean"]
    feature_engineer["feature_engineer"]
    feature_store_sync["feature_store_sync"]
    reduce_dimensions["reduce_dimensions"]
    train["train"]
    tune["tune<br/>(Vizier)"]
    evaluate["evaluate"]
    explain["explain<br/>(Explainable AI)"]
    register["register"]
    deploy["deploy"]

    ingest -->|Parquet| validate
    validate -->|Parquet +<br/>anomaly report| dlp_scan
    dlp_scan -->|Parquet +<br/>DLP findings| harmonize
    harmonize -->|Parquet| clean
    clean -->|Parquet| feature_engineer
    feature_engineer -->|Parquet| feature_store_sync
    feature_store_sync -->|Feature vectors| reduce_dimensions
    reduce_dimensions -->|Reduced Parquet| train
    train -->|Model pickle +<br/>metrics| tune
    tune -->|Best model pickle| evaluate
    evaluate -->|Eval report| explain
    explain -->|SHAP values +<br/>feature attributions| register
    register -->|Model URI| deploy
```

---

## Data Flow

End-to-end data movement from source tables through prediction serving.

```mermaid
sequenceDiagram
    participant BQ as BigQuery<br/>(Student Tables)
    participant GCS as Cloud Storage<br/>(Staging)
    participant Pipeline as Vertex AI<br/>Pipeline
    participant FS as Feature Store
    participant Registry as Model Registry
    participant Endpoint as Prediction<br/>Endpoint
    participant Log as BigQuery<br/>(Prediction Log)

    BQ->>GCS: Export student records (Parquet)
    GCS->>Pipeline: Ingest staged data
    Pipeline->>Pipeline: Validate → DLP → Harmonize → Clean
    Pipeline->>FS: Sync engineered features
    Pipeline->>Pipeline: Reduce → Train → Tune → Evaluate → Explain
    Pipeline->>Registry: Register champion model
    Registry->>Endpoint: Deploy model version

    Note over Endpoint,Log: Serving path
    Endpoint->>Log: Log predictions to BigQuery
    FS-->>Endpoint: Online feature lookup
```

---

## Infrastructure Topology

VPC layout, service perimeter, service accounts, and encryption keys.

```mermaid
flowchart TB
    subgraph VPC["VPC: meridian-vpc"]
        direction TB
        subgraph Subnet["Subnet: meridian-subnet (10.0.0.0/24)"]
            Pipeline_SA["pipeline-sa"]
            Serving_SA["serving-sa"]
            Monitoring_SA["monitoring-sa"]
        end
        NAT["Cloud NAT"]
        FW["Firewall Rules<br/>deny-all-ingress<br/>allow-internal<br/>allow-health-checks"]
    end

    subgraph Perimeter["VPC Service Controls Perimeter"]
        direction LR
        VertexAI["Vertex AI"]
        BigQuery["BigQuery"]
        GCS["Cloud Storage"]
        KMS["Cloud KMS"]
        DLP["Cloud DLP"]
        SecretMgr["Secret Manager"]
    end

    subgraph KeyRing["KMS Key Ring: meridian-keyring"]
        BQ_Key["BQ encryption key"]
        GCS_Key["GCS encryption key"]
    end

    VPC --- Perimeter
    Pipeline_SA -->|roles:<br/>aiplatform.user<br/>bigquery.dataEditor<br/>storage.objectAdmin| Perimeter
    Serving_SA -->|roles:<br/>aiplatform.predictor<br/>bigquery.dataViewer| Perimeter
    Monitoring_SA -->|roles:<br/>monitoring.viewer<br/>logging.viewer| Perimeter
    KMS --- KeyRing
    BQ_Key -.->|CMEK| BigQuery
    GCS_Key -.->|CMEK| GCS
```

---

## Security Architecture

Five-layer defense-in-depth (per ADR 004).

```mermaid
flowchart TB
    subgraph L1["Layer 1: Network Perimeter"]
        VPCSC["VPC Service Controls<br/>Block exfiltration of data<br/>outside trusted perimeter"]
    end

    subgraph L2["Layer 2: Identity & Access"]
        IAM["IAM Least-Privilege<br/>3 dedicated service accounts<br/>No user-managed keys"]
    end

    subgraph L3["Layer 3: Encryption"]
        CMEK["CMEK via Cloud KMS<br/>Customer-managed keys<br/>for BQ and GCS at rest"]
    end

    subgraph L4["Layer 4: Data Protection"]
        DLP["Cloud DLP<br/>PII detection and redaction<br/>FERPA compliance"]
    end

    subgraph L5["Layer 5: Audit"]
        Audit["Cloud Audit Logs<br/>Admin + Data Access logs<br/>Compliance trail"]
    end

    L1 --> L2 --> L3 --> L4 --> L5

    style L1 fill:#e8f5e9,stroke:#2e7d32
    style L2 fill:#e3f2fd,stroke:#1565c0
    style L3 fill:#fff3e0,stroke:#ef6c00
    style L4 fill:#fce4ec,stroke:#c62828
    style L5 fill:#f3e5f5,stroke:#6a1b9a
```

---

## Serving Architecture

Request flow from client through the prediction endpoint, with fallback chain.

```mermaid
flowchart LR
    Client["Client"]
    GLB["Global Load<br/>Balancer"]
    Armor["Cloud Armor<br/>(WAF)"]
    Endpoints["Cloud<br/>Endpoints"]
    FastAPI["FastAPI Container<br/>(Cloud Run /<br/>Vertex Prediction)"]

    Client --> GLB --> Armor --> Endpoints --> FastAPI

    subgraph Fallback["Fallback Chain (in order)"]
        direction TB
        F1["1. Live Model<br/>(Vertex Endpoint)"]
        F2["2. Redis Cache<br/>(Memorystore)"]
        F3["3. Batch Predictions<br/>(BigQuery)"]
        F4["4. Default Score<br/>(0.5)"]
        F1 -->|miss/error| F2
        F2 -->|miss/error| F3
        F3 -->|miss/error| F4
    end

    FastAPI --> Fallback
```

---

## Monitoring & Alerting

Drift detection triggers automatic retraining; three dashboards and three alert policies provide observability.

```mermaid
flowchart LR
    MM["Model Monitoring<br/>(Vertex AI)"]
    PS["Pub/Sub<br/>(drift-alerts topic)"]
    CF["Cloud Function<br/>(trigger-retrain)"]
    Pipeline["Vertex AI Pipeline<br/>(retraining run)"]

    MM -->|drift detected| PS
    PS --> CF
    CF -->|trigger| Pipeline

    subgraph Dashboards["Cloud Monitoring Dashboards"]
        D1["Pipeline Dashboard<br/>step latency, failures,<br/>data volume"]
        D2["Model Dashboard<br/>accuracy, drift score,<br/>feature distributions"]
        D3["Endpoint Dashboard<br/>latency p50/p99,<br/>error rate, QPS"]
    end

    subgraph Alerts["Alert Policies"]
        A1["Pipeline failure<br/>→ PagerDuty"]
        A2["Drift threshold<br/>exceeded → email"]
        A3["Endpoint error rate<br/>> 1% → PagerDuty"]
    end

    MM --> Dashboards
    MM --> Alerts
```

---

## GCP Products

| GCP Product | Role in Meridian | FDE Competency |
|---|---|---|
| Vertex AI Pipelines | Orchestrate 14-stage ML pipeline | ML Pipeline Orchestration |
| Vertex AI Experiments | Track training runs and metrics | Experiment Tracking |
| Vertex AI Feature Store | Online/offline feature serving | Feature Management |
| Vertex AI Model Registry | Model versioning and lineage | Model Management |
| Vertex AI Model Monitoring | Drift detection and alerts | Model Monitoring |
| Vertex AI TensorBoard | Training visualization | Experiment Tracking |
| Vertex AI Vizier | Hyperparameter tuning | AutoML / Tuning |
| Vertex AI Explainable AI | SHAP values, feature attributions | Model Explainability |
| Vertex AI Prediction | Online serving endpoint | Model Serving |
| BigQuery | Source data, prediction logs, analytics | Data Warehousing |
| Cloud Storage | Pipeline artifacts, staged data (Parquet) | Object Storage |
| Cloud KMS | CMEK for BQ and GCS encryption at rest | Encryption Management |
| Secret Manager | API keys, DB credentials | Secrets Management |
| Cloud DLP | PII detection/redaction (FERPA) | Data Protection |
| VPC Service Controls | Network perimeter around services | Network Security |
| Cloud Monitoring | Dashboards and metrics | Observability |
| Cloud Logging | Structured pipeline and serving logs | Observability |
| Cloud Trace | Request latency tracing | Observability |
| Cloud Armor | WAF rules on load balancer | Application Security |
| Memorystore (Redis) | Prediction cache (fallback layer 2) | Caching |
| Cloud Endpoints | API management and auth | API Management |
| Cloud Functions | Drift-to-retrain trigger | Event-Driven Compute |
| Pub/Sub | Drift alert message bus | Messaging |
| Cloud Build | CI/CD for pipeline and infrastructure | Build / Deploy |
| Cloud Audit Logs | Admin + data access compliance trail | Compliance |
| Cloud Run | FastAPI serving container | Serverless Compute |
| Terraform | Infrastructure as Code for all resources | IaC |
