import os
import requests
from typing import Dict, Any, Optional
from app.models.lakeview_model import LakeviewDashboard


class LakeviewAPIClient:
    """REST and SDK API Client for creating and publishing Databricks Lakeview Dashboards."""

    def __init__(self, host: str = None, token: str = None):
        self.host = (host or os.environ.get("DATABRICKS_HOST", "")).rstrip("/")
        self.token = token or os.environ.get("DATABRICKS_TOKEN", "")

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def create_dashboard(
        self,
        display_name: str,
        serialized_dashboard: str,
        warehouse_id: str,
        parent_path: str = "/Shared"
    ) -> Dict[str, Any]:
        """Create a new Lakeview dashboard via REST API."""
        url = f"{self.host}/api/2.0/lakeview/dashboards"
        payload = {
            "display_name": display_name,
            "serialized_dashboard": serialized_dashboard,
            "warehouse_id": warehouse_id,
            "parent_path": parent_path,
        }
        response = requests.post(url, headers=self._headers(), json=payload)
        response.raise_for_status()
        return response.json()

    def publish_dashboard(
        self,
        dashboard_id: str,
        warehouse_id: str,
        embed_credentials: bool = True
    ) -> Dict[str, Any]:
        """Publish an existing Lakeview dashboard via REST API."""
        url = f"{self.host}/api/2.0/lakeview/dashboards/{dashboard_id}/published"
        payload = {
            "embed_credentials": embed_credentials,
            "warehouse_id": warehouse_id,
        }
        response = requests.post(url, headers=self._headers(), json=payload)
        response.raise_for_status()
        return response.json()

    def deploy_with_sdk(
        self,
        display_name: str,
        serialized_dashboard: str,
        warehouse_id: str
    ) -> Dict[str, Any]:
        """Deploy dashboard via databricks-sdk WorkspaceClient."""
        from databricks.sdk import WorkspaceClient
        from databricks.sdk.service.dashboards import Dashboard

        w = WorkspaceClient(host=self.host, token=self.token)
        result = w.lakeview.create(
            dashboard=Dashboard(
                display_name=display_name,
                serialized_dashboard=serialized_dashboard,
                warehouse_id=warehouse_id,
            )
        )
        w.lakeview.publish(
            dashboard_id=result.dashboard_id,
            embed_credentials=True,
            warehouse_id=warehouse_id,
        )
        return {
            "dashboard_id": result.dashboard_id,
            "path": result.path,
            "published_url": f"{self.host}/dashboardsv3/{result.dashboard_id}/published"
        }
