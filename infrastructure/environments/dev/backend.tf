# GCS backend for Terraform state.
# Usage: terraform init -backend-config="bucket=meridian-tfstate-dev-<project_id>"
terraform {
  backend "gcs" {
    prefix = "terraform/state"
  }
}
