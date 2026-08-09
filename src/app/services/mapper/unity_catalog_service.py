"""
unity_catalog_service.py — Databricks Unity Catalog Client (SDK & Hive Metastore Fallback)
========================================================================================
Connects to Databricks workspace and reads Unity Catalog metadata:
catalogs, schemas, tables. Also supports SQL statement execution
and file upload to UC Volumes for auto-table-creation.

Uses the official Databricks Python SDK with transparent fallback to
hive_metastore (via SQL Warehouse execution) when Unity Catalog is not enabled.
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
    """Stateless client for Databricks Unity Catalog APIs using the SDK with hive_metastore fallback."""

    # HTTP connect/read timeout for SDK calls (seconds).
    # Prevents hanging when the Databricks host is unreachable or slow.
    HTTP_TIMEOUT_SECONDS = 15

    @staticmethod
    def _client(host: str, token: str) -> WorkspaceClient:
        """Create a WorkspaceClient for the given host/token pair."""
        from databricks.sdk.config import Config
        cfg = Config(
            host=host.rstrip("/"),
            token=token,
            http_timeout_seconds=UnityCatalogService.HTTP_TIMEOUT_SECONDS,
        )
        return WorkspaceClient(config=cfg)

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

    # ── SQL Fallback Helpers ─────────────────────────────────────────

    @staticmethod
    def _list_schemas_via_sql(
        host: str, token: str, warehouse_id: str, catalog: str
    ) -> List[Dict[str, Any]]:
        """Fallback to list schemas using SQL execution if UC API fails."""
        try:
            res = UnityCatalogService.execute_sql(host, token, warehouse_id, f"SHOW SCHEMAS IN `{catalog}`")
            rows = res.get("result", {}).get("data_array", [])
            schemas = []
            for r in rows:
                if r and len(r) > 0:
                    name = r[0]
                    if name != "information_schema":
                        schemas.append({"name": name, "catalog_name": catalog})
            return schemas if schemas else [{"name": "default", "catalog_name": catalog}]
        except Exception as e:
            logger.warning("Failed to list schemas via SQL fallback: %s", str(e))
            return [{"name": "default", "catalog_name": catalog}]

    @staticmethod
    def _list_tables_via_sql(
        host: str, token: str, warehouse_id: str, catalog: str, schema: str
    ) -> List[Dict[str, Any]]:
        """Fallback to list tables using SQL execution if UC API fails."""
        try:
            res = UnityCatalogService.execute_sql(host, token, warehouse_id, f"SHOW TABLES IN `{catalog}`.`{schema}`")
            rows = res.get("result", {}).get("data_array", [])
            tables = []
            for r in rows:
                if r and len(r) >= 2:
                    # SHOW TABLES returns (database, tableName, isTemporary) or (tableName, isTemporary)
                    tbl_name = r[1] if len(r) >= 3 else r[0]
                    tables.append({
                        "name": tbl_name,
                        "catalog_name": catalog,
                        "schema_name": schema,
                        "table_type": "MANAGED",
                    })
            return tables
        except Exception as e:
            logger.warning("Failed to list tables via SQL fallback: %s", str(e))
            return []

    # ── Catalog / Schema / Table Listing ──────────────────────────────

    @staticmethod
    def list_catalogs(host: str, token: str, warehouse_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all catalogs in the workspace.

        Falls back to hive_metastore if Unity Catalog is not enabled.
        """
        try:
            w = UnityCatalogService._client(host, token)
            catalogs = list(w.catalogs.list())
            return [c.as_dict() for c in catalogs]
        except (NotFound, UnityCatalogError) as e:
            status_code = getattr(e, "status_code", 0)
            if isinstance(e, NotFound) or status_code == 404 or "not found" in str(e).lower():
                logger.info("Unity Catalog not found on workspace. Falling back to hive_metastore.")
                return [{"name": "hive_metastore", "comment": "Legacy Hive Metastore (Fallback)"}]
            raise
        except Exception as e:
            UnityCatalogService._handle_error("Failed to list catalogs", e)

    @staticmethod
    def list_schemas(
        host: str, token: str, catalog: str, warehouse_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List all schemas in a catalog.

        Falls back to SQL execution if Unity Catalog API fails.
        """
        if catalog == "hive_metastore" and warehouse_id:
            return UnityCatalogService._list_schemas_via_sql(host, token, warehouse_id, catalog)

        try:
            w = UnityCatalogService._client(host, token)
            schemas = list(w.schemas.list(catalog_name=catalog))
            return [s.as_dict() for s in schemas]
        except (NotFound, UnityCatalogError) as e:
            status_code = getattr(e, "status_code", 0)
            if warehouse_id and (isinstance(e, NotFound) or status_code == 404 or "not found" in str(e).lower()):
                return UnityCatalogService._list_schemas_via_sql(host, token, warehouse_id, catalog)
            if isinstance(e, NotFound) or status_code == 404 or "not found" in str(e).lower():
                return [{"name": "default", "catalog_name": catalog}]
            raise
        except Exception as e:
            if warehouse_id:
                return UnityCatalogService._list_schemas_via_sql(host, token, warehouse_id, catalog)
            UnityCatalogService._handle_error(
                f"Failed to list schemas in '{catalog}'", e
            )

    @staticmethod
    def list_tables(
        host: str, token: str, catalog: str, schema: str, warehouse_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List all tables in a schema.

        Falls back to SQL execution if Unity Catalog API fails.
        """
        if catalog == "hive_metastore" and warehouse_id:
            return UnityCatalogService._list_tables_via_sql(host, token, warehouse_id, catalog, schema)

        try:
            w = UnityCatalogService._client(host, token)
            tables = list(w.tables.list(catalog_name=catalog, schema_name=schema))
            return [t.as_dict() for t in tables]
        except (NotFound, UnityCatalogError) as e:
            status_code = getattr(e, "status_code", 0)
            if warehouse_id and (isinstance(e, NotFound) or status_code == 404 or "not found" in str(e).lower()):
                return UnityCatalogService._list_tables_via_sql(host, token, warehouse_id, catalog, schema)
            if isinstance(e, NotFound) or status_code == 404 or "not found" in str(e).lower():
                return []
            raise
        except Exception as e:
            if warehouse_id:
                return UnityCatalogService._list_tables_via_sql(host, token, warehouse_id, catalog, schema)
            UnityCatalogService._handle_error(
                f"Failed to list tables in '{catalog}.{schema}'", e
            )

    @staticmethod
    def table_exists(
        host: str, token: str, full_name: str, warehouse_id: Optional[str] = None
    ) -> bool:
        """Check if a table exists in Unity Catalog or Hive Metastore.

        Args:
            full_name: Three-part or two-part name like 'catalog.schema.table'

        Returns:
            True if table exists, False otherwise.
        """
        try:
            w = UnityCatalogService._client(host, token)
            w.tables.get(full_name=full_name)
            return True
        except Exception:
            parts = full_name.split(".")
            if len(parts) == 3:
                cat, sch, tbl = parts
                try:
                    tbls = UnityCatalogService.list_tables(host, token, cat, sch, warehouse_id=warehouse_id)
                    return any(t.get("name", "").lower() == tbl.lower() for t in tbls)
                except Exception:
                    pass
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

    @staticmethod
    def get_table_columns(
        host: str, token: str, full_name: str, warehouse_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get detailed column metadata for a table.

        Uses the SDK tables.get() API which returns columns with:
        name, type_text, type_name, nullable, comment, position.

        Falls back to DESCRIBE TABLE via SQL if SDK fails.
        """
        # Try SDK first
        try:
            w = UnityCatalogService._client(host, token)
            table = w.tables.get(full_name=full_name)
            table_dict = table.as_dict()
            columns = table_dict.get("columns", [])
            if columns:
                return [
                    {
                        "name": col.get("name", ""),
                        "data_type": col.get("type_text", col.get("type_name", "")),
                        "nullable": col.get("nullable", True),
                        "comment": col.get("comment", ""),
                        "position": col.get("position", 0),
                        "is_partition": col.get("partition_index") is not None,
                    }
                    for col in columns
                ]
        except Exception:
            pass

        # Fallback: DESCRIBE TABLE via SQL
        if warehouse_id:
            try:
                res = UnityCatalogService.execute_sql(
                    host, token, warehouse_id,
                    f"DESCRIBE TABLE `{full_name}`"
                )
                rows = res.get("result", {}).get("data_array", [])
                columns = []
                for i, r in enumerate(rows):
                    if r and len(r) >= 2:
                        col_name = r[0] or ""
                        col_type = r[1] or ""
                        comment = r[2] if len(r) > 2 else ""
                        # Skip partition info section markers
                        if col_name.startswith("#") or col_name == "":
                            continue
                        columns.append({
                            "name": col_name.strip(),
                            "data_type": col_type.strip(),
                            "nullable": True,
                            "comment": (comment or "").strip(),
                            "position": i,
                            "is_partition": False,
                        })
                return columns
            except Exception as e:
                logger.debug("Failed to describe table %s via SQL: %s", full_name, str(e))

        return []

    @staticmethod
    def get_table_constraints(
        host: str, token: str, warehouse_id: str, full_name: str
    ) -> Dict[str, Any]:
        """Discover primary and foreign key constraints for a table.

        Uses DESCRIBE TABLE EXTENDED and SHOW TABLE PROPERTIES to find constraints.

        Returns dict with keys: primary_keys (list[str]), foreign_keys (list[dict]).
        """
        result = {"primary_keys": [], "foreign_keys": []}

        try:
            # Try to get PK info from DESCRIBE EXTENDED
            res = UnityCatalogService.execute_sql(
                host, token, warehouse_id,
                f"DESCRIBE TABLE EXTENDED `{full_name}`"
            )
            rows = res.get("result", {}).get("data_array", [])
            in_constraints = False
            for r in rows:
                if not r or len(r) < 2:
                    continue
                key = (r[0] or "").strip().lower()
                val = (r[1] or "").strip()
                if "constraint" in key or "primary key" in key:
                    in_constraints = True
                if in_constraints and "primary" in key.lower():
                    # Parse PK columns from value like "(col1, col2)"
                    import re as _re
                    pk_cols = _re.findall(r'`?(\w+)`?', val)
                    result["primary_keys"].extend(pk_cols)
        except Exception as e:
            logger.debug("Could not get constraints for %s: %s", full_name, str(e))

        try:
            # Try INFORMATION_SCHEMA for FK relationships
            parts = full_name.split(".")
            if len(parts) == 3:
                catalog, schema, table = parts
                fk_sql = (
                    f"SELECT tc.constraint_name, kcu.column_name, "
                    f"ccu.table_catalog, ccu.table_schema, ccu.table_name, ccu.column_name AS ref_column "
                    f"FROM `{catalog}`.information_schema.table_constraints tc "
                    f"JOIN `{catalog}`.information_schema.key_column_usage kcu "
                    f"ON tc.constraint_name = kcu.constraint_name "
                    f"JOIN `{catalog}`.information_schema.constraint_column_usage ccu "
                    f"ON tc.constraint_name = ccu.constraint_name "
                    f"WHERE tc.table_name = '{table}' "
                    f"AND tc.table_schema = '{schema}' "
                    f"AND tc.constraint_type = 'FOREIGN KEY'"
                )
                res = UnityCatalogService.execute_sql(host, token, warehouse_id, fk_sql)
                rows = res.get("result", {}).get("data_array", [])
                for r in rows:
                    if r and len(r) >= 6:
                        result["foreign_keys"].append({
                            "column": r[1],
                            "ref_catalog": r[2],
                            "ref_schema": r[3],
                            "ref_table": r[4],
                            "ref_column": r[5],
                        })
        except Exception as e:
            logger.debug("Could not get FK constraints for %s: %s", full_name, str(e))

        return result

    @staticmethod
    def get_table_properties(
        host: str, token: str, warehouse_id: str, full_name: str
    ) -> Dict[str, Any]:
        """Get table properties and statistics.

        Returns dict with: properties, row_count, partition_columns.
        """
        result = {"properties": {}, "row_count": None, "partition_columns": []}
        try:
            res = UnityCatalogService.execute_sql(
                host, token, warehouse_id,
                f"SHOW TABLE PROPERTIES `{full_name}`"
            )
            rows = res.get("result", {}).get("data_array", [])
            for r in rows:
                if r and len(r) >= 2:
                    key = (r[0] or "").strip()
                    val = (r[1] or "").strip()
                    result["properties"][key] = val
                    if "numRows" in key or "spark.sql.statistics.numRows" in key:
                        try:
                            result["row_count"] = int(val)
                        except ValueError:
                            pass
        except Exception as e:
            logger.debug("Could not get properties for %s: %s", full_name, str(e))

        return result

    # ── Search ────────────────────────────────────────────────────────


    @staticmethod
    def search_tables(
        host: str, token: str, query: str, max_results: int = 20, warehouse_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search for tables across all catalogs by name keyword."""
        query_lower = query.lower().strip()
        if not query_lower:
            return []

        results: List[Dict[str, Any]] = []
        try:
            catalogs = UnityCatalogService.list_catalogs(host, token, warehouse_id=warehouse_id)
        except UnityCatalogError:
            return []

        for cat in catalogs:
            cat_name = cat.get("name", "")
            if cat_name in ("system", "__databricks_internal"):
                continue

            try:
                schemas = UnityCatalogService.list_schemas(host, token, cat_name, warehouse_id=warehouse_id)
            except UnityCatalogError:
                continue

            for sch in schemas:
                sch_name = sch.get("name", "")
                if sch_name == "information_schema":
                    continue

                try:
                    tables = UnityCatalogService.list_tables(
                        host, token, cat_name, sch_name, warehouse_id=warehouse_id
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
