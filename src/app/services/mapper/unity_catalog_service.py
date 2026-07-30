"""
unity_catalog_service.py — Databricks Unity Catalog Client (SDK)
====================================================================
Connects to Databricks workspace and reads Unity Catalog metadata:
catalogs, schemas, tables. Also supports SQL statement execution
and file upload to UC Volumes for auto-table-creation.

Uses the official Databricks Python SDK instead of raw REST calls.
All methods are stateless — host/token passed per-call so the service
can work with multiple Databricks connections simultaneously.
"""

import io
import logging
import time
from typing import Any, Dict, List, Optional

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import (
    DatabricksError,
    NotFound,
    PermissionDenied,
    Unauthenticated,
)
from databricks.sdk.service.sql import Disposition, StatementState

logger = logging.getLogger(__name__)

# Timeout for SQL statement execution polling (seconds)
SQL_POLL_TIMEOUT = 120
SQL_POLL_INTERVAL = 2


class UnityCatalogError(Exception):
    """Raised when a Unity Catalog API call fails."""
    def __init__(self, message: str, status_code: int = 0):
        self.status_code = status_code
        super().__init__(message)


class UnityCatalogService:
    """Stateless client for Databricks Unity Catalog APIs using the SDK."""

    @staticmethod
    def _client(host: str, token: str) -> WorkspaceClient:
        """Create a WorkspaceClient for the given host/token pair."""
        return WorkspaceClient(
            host=host.rstrip("/"),
            token=token,
        )

    @staticmethod
    def _handle_error(operation: str, e: Exception) -> None:
        """Convert SDK exceptions to UnityCatalogError with clear messages."""
        if isinstance(e, Unauthenticated):
            raise UnityCatalogError(
                f"{operation}: Authentication failed. Check your PAT token.",
                status_code=401,
            ) from e
        elif isinstance(e, PermissionDenied):
            raise UnityCatalogError(
                f"{operation}: Permission denied. Ensure the token has sufficient privileges.",
                status_code=403,
            ) from e
        elif isinstance(e, NotFound):
            raise UnityCatalogError(
                f"{operation}: Resource not found. Verify Unity Catalog is enabled "
                "and a metastore is attached to the workspace.",
                status_code=404,
            ) from e
        elif isinstance(e, DatabricksError):
            raise UnityCatalogError(
                f"{operation}: {str(e)}",
                status_code=getattr(e, 'status_code', 0),
            ) from e
        else:
            raise UnityCatalogError(
                f"{operation}: Connection error — {str(e)}",
            ) from e

    # ── Catalog / Schema / Table Listing ──────────────────────────────

    @staticmethod
    def list_catalogs(host: str, token: str) -> List[Dict[str, Any]]:
        """List all catalogs in the workspace.

        Returns list of dicts with keys: name, comment, owner, etc.
        """
        try:
            w = UnityCatalogService._client(host, token)
            catalogs = list(w.catalogs.list())
            return [c.as_dict() for c in catalogs]
        except UnityCatalogError:
            raise
        except Exception as e:
            UnityCatalogService._handle_error("Failed to list catalogs", e)

    @staticmethod
    def list_schemas(host: str, token: str, catalog: str) -> List[Dict[str, Any]]:
        """List all schemas in a catalog.

        Returns list of dicts with keys: name, catalog_name, comment, etc.
        """
        try:
            w = UnityCatalogService._client(host, token)
            schemas = list(w.schemas.list(catalog_name=catalog))
            return [s.as_dict() for s in schemas]
        except UnityCatalogError:
            raise
        except Exception as e:
            UnityCatalogService._handle_error(
                f"Failed to list schemas in '{catalog}'", e
            )

    @staticmethod
    def list_tables(
        host: str, token: str, catalog: str, schema: str
    ) -> List[Dict[str, Any]]:
        """List all tables in a schema.

        Returns list of dicts with keys: name, catalog_name, schema_name,
        table_type, columns, etc.
        """
        try:
            w = UnityCatalogService._client(host, token)
            tables = list(w.tables.list(catalog_name=catalog, schema_name=schema))
            return [t.as_dict() for t in tables]
        except UnityCatalogError:
            raise
        except Exception as e:
            UnityCatalogService._handle_error(
                f"Failed to list tables in '{catalog}.{schema}'", e
            )

    @staticmethod
    def table_exists(host: str, token: str, full_name: str) -> bool:
        """Check if a table exists in Unity Catalog.

        Args:
            full_name: Three-part name like 'catalog.schema.table'

        Returns:
            True if table exists, False otherwise.
        """
        try:
            w = UnityCatalogService._client(host, token)
            w.tables.get(full_name=full_name)
            return True
        except NotFound:
            return False
        except Exception:
            return False

    @staticmethod
    def get_table_info(
        host: str, token: str, full_name: str
    ) -> Optional[Dict[str, Any]]:
        """Get detailed table info including columns.

        Returns dict with keys: name, catalog_name, schema_name, columns, etc.
        Returns None if table does not exist.
        """
        try:
            w = UnityCatalogService._client(host, token)
            table = w.tables.get(full_name=full_name)
            return table.as_dict()
        except NotFound:
            return None
        except Exception:
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

        Uses the SDK Statement Execution API. Polls for completion.

        Returns:
            Dict with keys: status, result (if SELECT), statement_id
        """
        try:
            w = UnityCatalogService._client(host, token)
            response = w.statement_execution.execute_statement(
                statement=sql,
                warehouse_id=warehouse_id,
                wait_timeout="0s",  # Async — we poll
            )

            statement_id = response.statement_id or ""
            status = response.status.state if response.status else None

            # Poll until completion
            elapsed = 0
            while status in (StatementState.PENDING, StatementState.RUNNING) and elapsed < SQL_POLL_TIMEOUT:
                time.sleep(SQL_POLL_INTERVAL)
                elapsed += SQL_POLL_INTERVAL
                response = w.statement_execution.get_statement(statement_id)
                status = response.status.state if response.status else None

            if status == StatementState.FAILED:
                error_msg = "Unknown SQL error"
                if response.status and response.status.error:
                    error_msg = response.status.error.message or error_msg
                raise UnityCatalogError(f"SQL execution failed: {error_msg}")

            return {
                "status": status.value if status else "UNKNOWN",
                "statement_id": statement_id,
                "result": response.result.as_dict() if response.result else {},
            }
        except UnityCatalogError:
            raise
        except Exception as e:
            UnityCatalogService._handle_error("SQL execution error", e)

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
        try:
            w = UnityCatalogService._client(host, token)
            w.files.upload(
                file_path=volume_path,
                contents=io.BytesIO(file_bytes),
                overwrite=True,
            )
            logger.info("Uploaded file to volume: %s", volume_path)
            return volume_path
        except UnityCatalogError:
            raise
        except Exception as e:
            UnityCatalogService._handle_error("Volume upload failed", e)

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
