# Model Card: Meridian Student Retention Classifier

## Model Details

| Field       | Value                                                                                      |
|-------------|--------------------------------------------------------------------------------------------|
| Name        | Meridian Student Retention Classifier                                                      |
| Version     | v1 (synthetic data baseline)                                                               |
| Type        | Binary classification (retained / not retained)                                            |
| Algorithms  | XGBoost, Random Forest, Logistic Regression, AdaBoost, Decision Tree, Gradient Boosting   |
| Framework   | scikit-learn / XGBoost with SMOTE class balancing                                          |
| Owner       | Institutional Research / Student Success                                                   |

---

## Intended Use

### Primary Use Case

Predict second-year student retention in higher education institutions. The model produces a binary prediction indicating whether a student is likely to be retained for their second year.

### Intended Users

- Institutional researchers
- Student success offices
- Enrollment management teams

### Out of Scope

This model should **not** be used for:

- Individual student decision-making (admissions accept/reject)
- Disciplinary actions or academic probation decisions
- Admissions screening or filtering
- Any automated decision with direct negative consequences for individual students

---

## Training Data

### Source

Synthetic student records generated with Faker, designed to mimic real institutional data patterns. Four tables are used:

| Table                  | Records  | Description                                  |
|------------------------|----------|----------------------------------------------|
| student_demographics   | ~50,000  | Age, gender, race/ethnicity, residency       |
| academic_records       | ~200,000 | GPA, credits, course grades                  |
| enrollment_events      | ~150,000 | Registration, withdrawal, transfer events    |
| financial_aid          | ~50,000  | Aid type, amount, unmet need                 |

### Target Variable

`second_year_ret_flag` -- Binary (0 = not retained, 1 = retained)

### Class Balance

Approximately 75% retained / 25% not retained, reflecting realistic institutional imbalance. Class imbalance is addressed via SMOTE (Synthetic Minority Over-sampling Technique) during training.

### PII Handling

Cloud DLP scan is applied to all input data before training to ensure FERPA compliance. PII columns are replaced with surrogate tokens.

---

## Evaluation

### Method

- Holdout test set with 80/20 train/test split (stratified by target variable)
- Model competition across all algorithm/SMOTE combinations

### Metrics

| Metric              | Description                                               |
|---------------------|-----------------------------------------------------------|
| Accuracy            | Overall correct predictions                               |
| AUC-ROC             | Area under the receiver operating characteristic curve    |
| True Positive Rate  | Sensitivity / recall for retained students                |
| True Negative Rate  | Specificity / recall for not-retained students            |
| F1 Score            | Harmonic mean of precision and recall                     |

### Model Selection

The best model is selected via automated competition (AMPE pattern). The winning model is chosen by a configurable primary metric (default: True Negative rate), prioritizing correct identification of at-risk students.

### Explainability

Feature importances are computed via three methods:

1. **Native importance** -- Algorithm-specific (e.g., XGBoost gain, Random Forest impurity)
2. **Permutation importance** -- Model-agnostic permutation-based ranking
3. **Vertex Explainable AI** -- SHAP-based explanations via Vertex AI integration

---

## Ethical Considerations

### Fairness

The model should be evaluated for bias across demographic groups -- including race, gender, and socioeconomic status -- before any production deployment. Disparate impact analysis is recommended as a prerequisite for institutional use.

### Privacy

- Training data is de-identified via Cloud DLP before model training
- PII columns are replaced with surrogate tokens (not simply removed)
- All data at rest is encrypted with customer-managed encryption keys (CMEK)

### FERPA Compliance

Five-layer defense-in-depth architecture:

1. **VPC Service Controls** -- Perimeter around all GCP resources
2. **IAM** -- Least-privilege service accounts and role bindings
3. **CMEK** -- Customer-managed encryption for all storage and compute
4. **Cloud DLP** -- Automated PII detection and redaction
5. **Cloud Audit Logs** -- Full audit trail of all data access

### Limitations

- **Synthetic data baseline** -- Trained on synthetic data; real-world performance will differ and must be validated before production use
- **External factors excluded** -- Does not account for pandemics, policy changes, economic shifts, or other macro-level disruptions
- **Not a sole decision basis** -- Should be used as one input among many in student success interventions, never as the sole determinant
- **Correlation is not causation** -- Features correlated with retention may not be causal; interventions should be designed with domain expertise

---

## Quantitative Analysis

### Training Configuration

- **6 algorithms** x **5 SMOTE strategies** = **30 model variants** per training run
- Winner selected via automated competition (best model on primary metric)
- Hyperparameter tuning via **Vertex AI Vizier** (Bayesian optimization)
- Feature importance tracked across training runs via **Vertex AI Experiments**

### Reproducibility

- All training artifacts (data snapshots, model binaries, metrics) stored in Cloud Storage with versioning
- Pipeline runs tracked in Vertex AI Pipelines with full lineage
- Experiment parameters and results logged to Vertex AI Experiments and TensorBoard
