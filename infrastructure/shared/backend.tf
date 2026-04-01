# GCS backend for Terraform state
# Usage: terraform init -backend-config="bucket=meridian-tfstate-<project_id>"
terraform {
  backend "gcs" {
    prefix = "terraform/state"
  }
}
