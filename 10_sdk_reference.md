# SDK Reference

This document covers Lakeview API usage across all Databricks SDKs and tools.

## Python SDK
[Verified]
```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import Dashboard, Schedule, Subscription

w = WorkspaceClient()

# Create
dashboard = w.lakeview.create(dashboard=Dashboard(
    display_name='My Dashboard', 
    warehouse_id='...', 
    serialized_dashboard='{...}'
))

# Get (with serialized_dashboard)
dashboard = w.lakeview.get(dashboard_id='...')

# Update
w.lakeview.update(
    dashboard_id='...', 
    dashboard=Dashboard(serialized_dashboard='{...}'), 
    etag='...'
)

# List
for d in w.lakeview.list():
    print(d.display_name)

# Publish
w.lakeview.publish(
    dashboard_id='...', 
    embed_credentials=True, 
    warehouse_id='...'
)

# Unpublish
w.lakeview.unpublish(dashboard_id='...')

# Trash
w.lakeview.trash(dashboard_id='...')

# Migrate legacy
w.lakeview.migrate(source_dashboard_id='...')

# Schedules
w.lakeview.create_schedule(dashboard_id='...', schedule=Schedule(...))
w.lakeview.list_schedules(dashboard_id='...')

# Subscriptions
w.lakeview.create_subscription(dashboard_id='...', schedule_id='...', subscription=Subscription(...))
```

## Go SDK
[Verified]
```go
package main

import (
    "context"
    "fmt"
    "github.com/databricks/databricks-sdk-go"
    "github.com/databricks/databricks-sdk-go/service/dashboards"
)

func main() {
    ctx := context.Background()
    w, err := databricks.NewWorkspaceClient()
    if err != nil {
        panic(err)
    }

    // Create
    dash, err := w.Lakeview.Create(ctx, dashboards.CreateDashboardRequest{
        Dashboard: dashboards.Dashboard{
            DisplayName: "My Dashboard",
            WarehouseId: "...",
            SerializedDashboard: "{...}",
        },
    })

    // Get
    dash, err = w.Lakeview.GetByDashboardId(ctx, "...")

    // Publish
    _, err = w.Lakeview.Publish(ctx, dashboards.PublishRequest{
        DashboardId: "...",
        EmbedCredentials: true,
        WarehouseId: "...",
    })
}
```

## CLI
[Verified]
```bash
databricks lakeview create --json '{...}'
databricks lakeview get <dashboard-id>
databricks lakeview publish <dashboard-id> --embed-credentials --warehouse-id <id>
databricks lakeview list
databricks bundle generate dashboard --existing-id <dashboard-id>
databricks bundle deploy
```

## Terraform
[Verified]
```hcl
resource "databricks_dashboard" "example" {
  display_name     = "My Dashboard"
  warehouse_id     = data.databricks_sql_warehouse.starter.id
  parent_path      = "/Shared/dashboards"
  file_path        = "${path.module}/dashboard.lvdash.json"
  embed_credentials = true
}
```

## Asset Bundles
[Verified]
```yaml
resources:
  dashboards:
    my_dashboard:
      display_name: My Dashboard
      file_path: src/dashboard.lvdash.json
      warehouse_id: ${var.warehouse_id}
```
