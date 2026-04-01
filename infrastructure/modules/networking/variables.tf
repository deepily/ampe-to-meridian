variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "vpc_sc_dry_run" {
  description = "Run VPC Service Controls in dry-run mode (true for dev, false for prod)"
  type        = bool
  default     = true
}

variable "access_level_members" {
  description = "List of members allowed through VPC Service Controls perimeter"
  type        = list( string )
  default     = []
}
