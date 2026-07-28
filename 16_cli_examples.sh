#!/bin/bash
# Databricks Lakeview CLI Examples

# Ensure DATABRICKS_HOST and DATABRICKS_TOKEN are set in your environment.

echo "--- Databricks Lakeview CLI Examples ---"

# 1. Create a dashboard
echo "[1] Creating Dashboard..."
CREATE_RES=$(databricks lakeview create --display-name "CLI Example Dashboard" --serialized-dashboard '{"pages": [{"name": "page1", "elements": []}]}' -o json)
DASHBOARD_ID=$(echo $CREATE_RES | jq -r '.dashboard_id')
echo "Created Dashboard ID: $DASHBOARD_ID"

# 2. Get dashboard
echo "[2] Getting Dashboard..."
databricks lakeview get $DASHBOARD_ID

# 3. Update dashboard
echo "[3] Updating Dashboard..."
databricks lakeview update $DASHBOARD_ID --display-name "CLI Example Dashboard - Updated" --serialized-dashboard '{"pages": [{"name": "page1", "elements": []}]}'

# 4. Publish dashboard with embed credentials
echo "[4] Publishing Dashboard..."
databricks lakeview publish $DASHBOARD_ID --embed-credentials

# 5. List all dashboards
echo "[5] Listing Dashboards..."
databricks lakeview list -o json | jq '.[] | {id: .dashboard_id, name: .display_name}'

# 6. Unpublish dashboard
echo "[6] Unpublishing Dashboard..."
databricks lakeview unpublish $DASHBOARD_ID

# 7. Export dashboard JSON (using get and jq)
echo "[7] Exporting Dashboard JSON..."
databricks lakeview get $DASHBOARD_ID -o json | jq -r '.serialized_dashboard' > export_${DASHBOARD_ID}.json
echo "Exported to export_${DASHBOARD_ID}.json"

# 8. Trash dashboard
echo "[8] Trashing Dashboard..."
databricks lakeview trash $DASHBOARD_ID

echo "--- CLI Examples Complete ---"
