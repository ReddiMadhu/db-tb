# Databricks Lakeview Terraform Examples

terraform {
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = ">= 1.30.0" # Minimum version for lakeview support
    }
  }
}

provider "databricks" {}

# Variables
variable "warehouse_id" {
  type        = string
  description = "The ID of the SQL Warehouse to use"
  default     = "xxxxxxxxxxxx"
}

variable "catalog" {
  type        = string
  description = "Default catalog for the dashboard"
  default     = "main"
}

variable "schema" {
  type        = string
  description = "Default schema for the dashboard"
  default     = "default"
}

# Data source for SQL Warehouse
data "databricks_sql_warehouse" "default" {
  id = var.warehouse_id
}

# Example 1: Dashboard with Inline JSON Definition
resource "databricks_dashboard" "inline_dashboard" {
  display_name         = "TF Inline Dashboard Example"
  parent_path          = "/Shared"
  serialized_dashboard = jsonencode({
    pages = [
      {
        name     = "page_1"
        elements = []
      }
    ]
  })
}

# Example 2: Dashboard using a File for JSON Definition
resource "databricks_dashboard" "file_dashboard" {
  display_name         = "TF File Dashboard Example"
  parent_path          = "/Shared"
  serialized_dashboard = file("${path.module}/dashboard_def.json")
}

# Example 3: Dashboard Permissions
resource "databricks_permissions" "dashboard_permissions" {
  dashboard_id = databricks_dashboard.file_dashboard.id

  access_control {
    group_name       = "users"
    permission_level = "CAN_RUN"
  }

  access_control {
    user_name        = "admin@example.com"
    permission_level = "CAN_MANAGE"
  }
}

# Example 4: Published Dashboard (assuming publish is managed via UI or API script, 
# as standard databricks_dashboard resource might not natively support publishing state directly in all versions, 
# but it represents the asset)
resource "databricks_dashboard" "prod_dashboard" {
  display_name         = "Production Sales Dashboard"
  parent_path          = "/Workspace/Production"
  serialized_dashboard = file("${path.module}/prod_dashboard_def.json")
}
