"""
unity_catalog_service.py — Databricks Unity Catalog REST API Client
====================================================================
Connects to Databricks workspace and reads Unity Catalog metadata:
catalogs, schemas, tables. Also supports SQL statement execution
and file upload to UC Volumes for auto-table-creation.

All methods are stateless — host/token passed per-call so the service
can work with multiple Databricks connections simultaneously.
"""

import requests
import time
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Timeout for REST API calls (seconds)
API_TIMEOUT = 30
# Timeout for SQL statement execution polling (seconds)
SQL_POLL_TIMEOUT = 120
SQL_POLL_INTERVAL = 2


class UnityCatalogError(Exception):
    """Raised when a Unity Catalog API call fails."""
    def __init__(self, message: str, status_code: int = 0):
        self.status_code = status_code
        super().__init__(message)


class UnityCatalogService:
    """Stateless REST client for Databricks Unity Catalog APIs."""

    @staticmethod
    def _headers(token: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @staticmethod
    def _base(host: str) -> str:
        return host.rstrip("/")

    # ── Catalog / Schema / Table Listing ──────────────────────────────

    @staticmethod
    def list_catalogs(host: str, token: str) -> List[Dict[str, Any]]:
        """List all catalogs in the workspace.

        Returns list of dicts with keys: name, comment, owner, etc.
        """
        url = f"{UnityCatalogService._base(host)}/api/2.1/unity-catalog/catalogs"
        try:
            resp = requests.get(
                url,
                headers=UnityCatalogService._headers(token),
                timeout=API_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json().get("catalogs", [])
        except requests.exceptions.HTTPError as e:
            raise UnityCatalogError(
                f"Failed to list catalogs: {e.response.text if e.response else str(e)}",
                status_code=e.response.status_code if e.response else 0,
            )
        except requests.exceptions.RequestException as e:
            raise UnityCatalogError(f"Connection error listing catalogs: {str(e)}")

    @staticmethod
    def list_schemas(host: str, token: str, catalog: str) -> List[Dict[str, Any]]:
        """List all schemas in a catalog.

        Returns list of dicts with keys: name, catalog_name, comment, etc.
        """
        url = f"{UnityCatalogService._base(host)}/api/2.1/unity-catalog/schemas"
        params = {"catalog_name": catalog}
        try:
            resp = requests.get(
                url,
                headers=UnityCatalogService._headers(token),
                params=params,
                timeout=API_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json().get("schemas", [])
        except requests.exceptions.HTTPError as e:
            raise UnityCatalogError(
                f"Failed to list schemas in '{catalog}': {e.response.text if e.response else str(e)}",
                status_code=e.response.status_code if e.response else 0,
            )
        except requests.exceptions.RequestException as e:
            raise UnityCatalogError(f"Connection error listing schemas: {str(e)}")

    @staticmethod
    def list_tables(
        host: str, token: str, catalog: str, schema: str
    ) -> List[Dict[str, Any]]:
        """List all tables in a schema.

        Returns list of dicts with keys: name, catalog_name, schema_name,
        table_type, columns, etc.
        """
        url = f"{UnityCatalogService._base(host)}/api/2.1/unity-catalog/tables"
        params = {"catalog_name": catalog, "schema_name": schema}
        try:
            resp = requests.get(
                url,
                headers=UnityCatalogService._headers(token),
                params=params,
                timeout=API_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json().get("tables", [])
        except requests.exceptions.HTTPError as e:
            raise UnityCatalogError(
                f"Failed to list tables in '{catalog}.{schema}': "
                f"{e.response.text if e.response else str(e)}",
                status_code=e.response.status_code if e.response else 0,
            )
        except requests.exceptions.RequestException as e:
            raise UnityCatalogError(f"Connection error listing tables: {str(e)}")

    @staticmethod
    def table_exists(host: str, token: str, full_name: str) -> bool:
        """Check if a table exists in Unity Catalog.

        Args:
            full_name: Three-part name like 'catalog.schema.table'

        Returns:
            True if table exists, False otherwise.
        """
        url = (
            f"{UnityCatalogService._base(host)}/api/2.1/unity-catalog/tables/{full_name}"
        )
        try:
            resp = requests.get(
                url,
                headers=UnityCatalogService._headers(token),
                timeout=API_TIMEOUT,
            )
            return resp.status_code == 200
        except requests.exceptions.RequestException:
            return False

    @staticmethod
    def get_table_info(
        host: str, token: str, full_name: str
    ) -> Optional[Dict[str, Any]]:
        """Get detailed table info including columns.

        Returns dict with keys: name, catalog_name, schema_name, columns, etc.
        Returns None if table does not exist.
        """
        url = (
            f"{UnityCatalogService._base(host)}/api/2.1/unity-catalog/tables/{full_name}"
        )
        try:
            resp = requests.get(
                url,
                headers=UnityCatalogService._headers(token),
                timeout=API_TIMEOUT,
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException:
            return None

    # ── Search ────────────────────────────────────────────────────────

    @staticmethod
    def search_tables(
        host: str, token: str, query: str, max_results: int = 20
    ) -> List[Dict[str, Any]]:
        """Search for tables across all catalogs by name keyword.

        Iterates catalogs → schemas → tables and filters by query string.
        Returns list of matching tables with full_name.
        """
        query_lower = query.lower().strip()
        if not query_lower:
            return []

        results: List[Dict[str, Any]] = []
        try:
            catalogs = UnityCatalogService.list_catalogs(host, token)
        except UnityCatalogError:
            return []

        for cat in catalogs:
            cat_name = cat.get("name", "")
            # Skip system catalogs
            if cat_name in ("system", "__databricks_internal"):
                continue

            try:
                schemas = UnityCatalogService.list_schemas(host, token, cat_name)
            except UnityCatalogError:
                continue

            for sch in schemas:
                sch_name = sch.get("name", "")
                if sch_name == "information_schema":
                    continue

                try:
                    tables = UnityCatalogService.list_tables(
                        host, token, cat_name, sch_name
                    )
                except UnityCatalogError:
                    continue

                for tbl in tables:
                    tbl_name = tbl.get("name", "")
                    full_name = f"{cat_name}.{sch_name}.{tbl_name}"

                    if query_lower in tbl_name.lower() or query_lower in full_name.lower():
                        results.append({
                            "catalog": cat_name,
                            "schema": sch_name,
                            "table": tbl_name,
                            "full_name": full_name,
                            "table_type": tbl.get("table_type", "MANAGED"),
                        })

                    if len(results) >= max_results:
                        return results

        return results

    # ── SQL Execution ─────────────────────────────────────────────────

    @staticmethod
    def execute_sql(
        host: str, token: str, warehouse_id: str, sql: str
    ) -> Dict[str, Any]:
        """Execute a SQL statement on a Databricks SQL Warehouse.

        Uses the SQL Statement Execution API. Polls for completion.

        Returns:
            Dict with keys: status, result (if SELECT), statement_id
        """
        url = f"{UnityCatalogService._base(host)}/api/2.0/sql/statements"
        payload = {
            "warehouse_id": warehouse_id,
            "statement": sql,
            "wait_timeout": "0s",  # Async — we poll
        }
        try:
            resp = requests.post(
                url,
                headers=UnityCatalogService._headers(token),
                json=payload,
                timeout=API_TIMEOUT,
            )
            resp.raise_for_status()
            result = resp.json()

            statement_id = result.get("statement_id", "")
            status = result.get("status", {}).get("state", "")

            # Poll until completion
            elapsed = 0
            while status in ("PENDING", "RUNNING") and elapsed < SQL_POLL_TIMEOUT:
                time.sleep(SQL_POLL_INTERVAL)
                elapsed += SQL_POLL_INTERVAL
                poll_url = f"{url}/{statement_id}"
                poll_resp = requests.get(
                    poll_url,
                    headers=UnityCatalogService._headers(token),
                    timeout=API_TIMEOUT,
                )
                poll_resp.raise_for_status()
                result = poll_resp.json()
                status = result.get("status", {}).get("state", "")

            if status == "FAILED":
                error_msg = result.get("status", {}).get("error", {}).get("message", "Unknown SQL error")
                raise UnityCatalogError(f"SQL execution failed: {error_msg}")

            return {
                "status": status,
                "statement_id": statement_id,
                "result": result.get("result", {}),
            }
        except requests.exceptions.HTTPError as e:
            raise UnityCatalogError(
                f"SQL execution API error: {e.response.text if e.response else str(e)}",
                status_code=e.response.status_code if e.response else 0,
            )
        except requests.exceptions.RequestException as e:
            raise UnityCatalogError(f"Connection error executing SQL: {str(e)}")

    # ── Volume File Upload ────────────────────────────────────────────

    @staticmethod
    def upload_to_volume(
        host: str,
        token: str,
        catalog: str,
        schema: str,
        volume: str,
        filename: str,
        file_bytes: bytes,
    ) -> str:
        """Upload a file to a Unity Catalog Volume.

        Args:
            volume: Volume name (must already exist)
            filename: Target filename in the volume
            file_bytes: Raw file content

        Returns:
            Volume path string: /Volumes/{catalog}/{schema}/{volume}/{filename}
        """
        volume_path = f"/Volumes/{catalog}/{schema}/{volume}/{filename}"
        url = f"{UnityCatalogService._base(host)}/api/2.0/fs/files{volume_path}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
        }
        try:
            resp = requests.put(
                url,
                headers=headers,
                data=file_bytes,
                timeout=120,  # Large file uploads may take longer
            )
            resp.raise_for_status()
            logger.info("Uploaded file to volume: %s", volume_path)
            return volume_path
        except requests.exceptions.HTTPError as e:
            raise UnityCatalogError(
                f"Volume upload failed: {e.response.text if e.response else str(e)}",
                status_code=e.response.status_code if e.response else 0,
            )
        except requests.exceptions.RequestException as e:
            raise UnityCatalogError(f"Connection error uploading to volume: {str(e)}")

    @staticmethod
    def create_table_from_volume(
        host: str,
        token: str,
        warehouse_id: str,
        catalog: str,
        schema: str,
        table_name: str,
        volume_path: str,
        file_format: str = "csv",
    ) -> str:
        """Create a Delta table from a file in a UC Volume using read_files().

        Returns:
            Full table name: catalog.schema.table_name
        """
        full_name = f"{catalog}.{schema}.{table_name}"
        sql = (
            f"CREATE TABLE IF NOT EXISTS {full_name} "
            f"AS SELECT * FROM read_files('{volume_path}', "
            f"format => '{file_format}', header => true)"
        )
        logger.info("Creating table %s from volume path %s", full_name, volume_path)
        UnityCatalogService.execute_sql(host, token, warehouse_id, sql)
        return full_name
