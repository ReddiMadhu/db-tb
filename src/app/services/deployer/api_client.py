"""
api_client.py — Databricks Lakeview API Client
===============================================
REST and SDK API Client for creating, publishing, updating, and managing
Databricks AI/BI (Lakeview) Dashboards.
"""

import os
import requests
from typing import Dict, Any, Optional


class LakeviewAPIClient:
    """REST and SDK API Client for managing Databricks Lakeview Dashboards."""

    def __init__(self, host: str = None, token: str = None):
        self.host = (host or os.environ.get("DATABRICKS_HOST", "")).rstrip("/")
        self.token = token or os.environ.get("DATABRICKS_TOKEN", "")

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def create_dashboard(
        self,
        display_name: str,
        serialized_dashboard: str,
        warehouse_id: str,
        parent_path: str = "/Shared",
        dataset_catalog: Optional[str] = None,
        dataset_schema: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new Lakeview dashboard via REST API."""
        url = f"{self.host}/api/2.0/lakeview/dashboards"
        params = {}
        if dataset_catalog:
            params["dataset_catalog"] = dataset_catalog
        if dataset_schema:
            params["dataset_schema"] = dataset_schema

        payload = {
            "display_name": display_name,
            "serialized_dashboard": serialized_dashboard,
            "warehouse_id": warehouse_id,
            "parent_path": parent_path,
        }
        response = requests.post(url, headers=self._headers(), params=params, json=payload)
        response.raise_for_status()
        return response.json()

    def get_dashboard(self, dashboard_id: str) -> Dict[str, Any]:
        """GET /api/2.0/lakeview/dashboards/{dashboard_id}"""
        url = f"{self.host}/api/2.0/lakeview/dashboards/{dashboard_id}"
        response = requests.get(url, headers=self._headers())
        response.raise_for_status()
        return response.json()

    def update_dashboard(
        self,
        dashboard_id: str,
        serialized_dashboard: Optional[str] = None,
        display_name: Optional[str] = None,
        warehouse_id: Optional[str] = None,
        etag: Optional[str] = None
    ) -> Dict[str, Any]:
        """PATCH /api/2.0/lakeview/dashboards/{dashboard_id}"""
        url = f"{self.host}/api/2.0/lakeview/dashboards/{dashboard_id}"
        payload: Dict[str, Any] = {}
        if serialized_dashboard:
            payload["serialized_dashboard"] = serialized_dashboard
        if display_name:
            payload["display_name"] = display_name
        if warehouse_id:
            payload["warehouse_id"] = warehouse_id
        if etag:
            payload["etag"] = etag

        response = requests.patch(url, headers=self._headers(), json=payload)
        response.raise_for_status()
        return response.json()

    def publish_dashboard(
        self,
        dashboard_id: str,
        warehouse_id: Optional[str] = None,
        embed_credentials: bool = True
    ) -> Dict[str, Any]:
        """Publish an existing Lakeview dashboard via REST API."""
        url = f"{self.host}/api/2.0/lakeview/dashboards/{dashboard_id}/published"
        payload: Dict[str, Any] = {"embed_credentials": embed_credentials}
        if warehouse_id:
            payload["warehouse_id"] = warehouse_id

        response = requests.post(url, headers=self._headers(), json=payload)
        response.raise_for_status()
        return response.json()

    def trash_dashboard(self, dashboard_id: str) -> Dict[str, Any]:
        """DELETE /api/2.0/lakeview/dashboards/{dashboard_id}"""
        url = f"{self.host}/api/2.0/lakeview/dashboards/{dashboard_id}"
        response = requests.delete(url, headers=self._headers())
        response.raise_for_status()
        return response.json() if response.text else {}

    def deploy_with_sdk(
        self,
        display_name: str,
        serialized_dashboard: str,
        warehouse_id: str,
        parent_path: str = "/Shared"
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
                parent_path=parent_path,
            )
        )
        w.lakeview.publish(
            dashboard_id=result.dashboard_id,
            embed_credentials=True,
            warehouse_id=warehouse_id,
        )
        return {
            "dashboard_id": result.dashboard_id,
            "path": getattr(result, "path", parent_path),
            "published_url": f"{self.host}/dashboardsv3/{result.dashboard_id}/published"
        }
