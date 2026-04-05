.PHONY: synth-data pipeline test chaos deploy destroy destroy-expensive lint help

PYTHON     := python
PYTEST     := pytest
TF_DIR     := infrastructure/environments/dev
TF         := terraform -chdir=$(TF_DIR)
TF_VARS    := -var-file=dev.tfvars
TF_BACKEND := -backend-config="bucket=meridian-tfstate-dev-ampe-to-meridian"

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

synth-data: ## Generate synthetic student data and load into BigQuery + GCS
	$(PYTHON) -m src.data_synthesis.student_generator
	$(PYTHON) -m src.data_synthesis.pii_injector
	$(PYTHON) -m src.data_synthesis.load_to_bigquery

pipeline: ## Run Vertex AI Pipeline end-to-end
	$(PYTHON) -m src.pipeline.vertex_pipeline

test: ## Run unit + integration tests
	$(PYTEST) tests/unit/ tests/integration/ -v --tb=short

test-unit: ## Run unit tests only
	$(PYTEST) tests/unit/ -v --tb=short

test-integration: ## Run integration tests only
	$(PYTEST) tests/integration/ -v --tb=short

chaos: ## Run chaos tests (drift injection, endpoint failure, data corruption)
	$(PYTEST) tests/chaos/ -v --tb=short

lint: ## Run linter
	ruff check src/ tests/

tf-init: ## Initialize Terraform (once per machine)
	$(TF) init $(TF_BACKEND)

tf-plan: ## Show planned Terraform changes
	$(TF) plan $(TF_VARS)

deploy: ## Deploy all Terraform infrastructure
	$(TF) init $(TF_BACKEND)
	$(TF) apply -auto-approve $(TF_VARS)

destroy: ## Tear down ALL resources
	$(TF) destroy -auto-approve $(TF_VARS)

destroy-expensive: ## Tear down only expensive resources (GLB, Feature Store, endpoints)
	$(TF) destroy -auto-approve $(TF_VARS) \
		-target=module.api \
		-target=module.vertex
