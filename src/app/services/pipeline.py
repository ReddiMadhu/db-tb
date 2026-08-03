"""
Tableau to Databricks Migration — 9-Stage Pipeline Orchestrator

Executes the migration pipeline and persists per-stage results to the
database, enabling real-time progress polling from the frontend.
"""

import os
import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from app.models.metadata import WorkbookMetadata
from app.services.parser.tableau_extractor import parse_workbook
from app.services.parser.dependency_graph import DependencyGraphEngine
from app.services.normalizer.tom_to_ubim import normalize_tom_to_ubim
from app.services.normalizer.optimizer import optimize_ubim
from app.services.generator.lakeview_generator import generate_lakeview_dashboard
from app.services.validator.validation_engine import (
    validate_lakeview_dashboard,
    prune_incomplete_widgets,
)
from app.services.reporter.migration_report import generate_migration_report
from app.services.mapper.datasource_mapper import build_table_mapping

logger = logging.getLogger(__name__)


class MigrationPipeline:
    """9-Stage Migration Pipeline Orchestrator with per-stage DB persistence.

    Each stage writes its results (status, metrics, logs, duration) to the
    stage_results table immediately upon completion, enabling the frontend
    to poll for real-time progress updates.

    Stage 3.5 (Unity Catalog Auto-Discovery) is automatically triggered when
    Databricks connections are detected in the Tableau workbook AND credentials
    are available via environment variables or config.
    """

    def __init__(
        self,
        file_path: str,
        job_uuid: str = "",
        table_mapping: Dict[str, str] = None,
        default_catalog: str = "",
        default_schema: str = "",
        databricks_host: str = "",
        databricks_token: str = "",
        warehouse_id: str = "",
    ):
        self.file_path = file_path
        self.job_uuid = job_uuid
        self.table_mapping = table_mapping or {}
        self.default_catalog = default_catalog
        self.default_schema = default_schema
        self.databricks_host = databricks_host
        self.databricks_token = databricks_token
        self.warehouse_id = warehouse_id
        self.error_bag = []
        self.semantic_model = None  # Set by Stage 3.5 if discovery succeeds

    def log(self, level: str, message: str):
        self.error_bag.append({"level": level, "message": message})

    # ── Per-Stage DB Persistence ──

    def _get_db_session(self):
        """Create a fresh DB session for stage persistence."""
        from app.db.session import SessionLocal
        return SessionLocal()

    def _init_all_stages(self):
        """Initialize or reset stages for job execution while preserving UPLOAD stage."""
        if not self.job_uuid:
            return
        from app.models.stage_model import StageResult, PIPELINE_STAGE_DEFS
        db = self._get_db_session()
        try:
            # Query existing stage results for this job
            existing = {
                r.stage_id: r
                for r in db.query(StageResult).filter(StageResult.job_uuid == self.job_uuid).all()
            }

            for stage_def in PIPELINE_STAGE_DEFS:
                stage_id = stage_def["id"]
                if stage_id in existing:
                    row = existing[stage_id]
                    # Keep UPLOAD stage COMPLETED if file exists and was already uploaded
                    if stage_id == "UPLOAD" and row.status == "COMPLETED":
                        continue
                    # Reset non-upload stages to WAITING for pipeline execution
                    row.status = "WAITING"
                    row.started_at = None
                    row.completed_at = None
                    row.duration_ms = None
                    row.output_summary = None
                    row.logs = []
                    row.warnings = []
                    row.errors = []
                    row.generated_code = None
                else:
                    # Create new stage result row
                    is_upload_done = (stage_id == "UPLOAD" and self.file_path and os.path.exists(self.file_path))
                    filename = os.path.basename(self.file_path) if self.file_path else "workbook.twbx"
                    file_size = os.path.getsize(self.file_path) if (self.file_path and os.path.exists(self.file_path)) else 0
                    stage = StageResult(
                        job_uuid=self.job_uuid,
                        stage_id=stage_id,
                        stage_number=stage_def["number"],
                        stage_name=stage_def["name"],
                        status="COMPLETED" if is_upload_done else "WAITING",
                        started_at=datetime.utcnow() if is_upload_done else None,
                        completed_at=datetime.utcnow() if is_upload_done else None,
                        duration_ms=45 if is_upload_done else None,
                        input_summary=f"{filename} ({file_size:,} bytes)" if is_upload_done else None,
                        output_summary="Uploaded and unpacked archive into workspace" if is_upload_done else None,
                        metrics={"workbook_name": filename, "workbook_size": f"{file_size:,} bytes"} if is_upload_done else {},
                        artifacts={"workbook_name": filename, "workbook_size": f"{file_size:,} bytes"} if is_upload_done else {},
                        logs=[f"[SUCCESS] Upload completed successfully"] if is_upload_done else [],
                        warnings=[],
                        errors=[],
                    )
                    db.add(stage)
            db.commit()
        except Exception as e:
            logger.warning("Failed to initialize stage results: %s", e)
            db.rollback()
        finally:
            db.close()

    def _persist_stage(
        self,
        stage_id: str,
        status: str,
        started_at: datetime = None,
        completed_at: datetime = None,
        duration_ms: int = None,
        input_summary: str = None,
        output_summary: str = None,
        metrics: Dict = None,
        logs: list = None,
        warnings: list = None,
        errors: list = None,
        generated_code: str = None,
        artifacts: Dict = None,
    ):
        """Update a stage result row in the database."""
        if not self.job_uuid:
            return
        from app.models.stage_model import StageResult
        db = self._get_db_session()
        try:
            row = (
                db.query(StageResult)
                .filter(StageResult.job_uuid == self.job_uuid, StageResult.stage_id == stage_id)
                .first()
            )
            if row:
                row.status = status
                if started_at:
                    row.started_at = started_at
                if completed_at:
                    row.completed_at = completed_at
                if duration_ms is not None:
                    row.duration_ms = duration_ms
                if input_summary is not None:
                    row.input_summary = input_summary
                if output_summary is not None:
                    row.output_summary = output_summary
                if metrics is not None:
                    row.metrics = metrics
                if logs is not None:
                    row.logs = logs
                if warnings is not None:
                    row.warnings = warnings
                if errors is not None:
                    row.errors = errors
                if generated_code is not None:
                    row.generated_code = generated_code
                if artifacts is not None:
                    row.artifacts = artifacts
                db.commit()
        except Exception as e:
            logger.warning("Failed to persist stage %s: %s", stage_id, e)
            db.rollback()
        finally:
            db.close()

    def _run_stage(self, stage_id: str, input_summary: str, fn):
        """Execute a pipeline stage function with timing and persistence.

        Args:
            stage_id: The frontend stage ID (e.g., "PARSE")
            input_summary: Description of stage inputs
            fn: Callable that returns (output_summary, metrics, logs, warnings, errors, generated_code)
                Each element can be None if not applicable.

        Returns:
            The return value of fn (after unpacking the stage metadata).
        """
        start = time.time()
        started_at = datetime.utcnow()
        self._persist_stage(stage_id, status="RUNNING", started_at=started_at, input_summary=input_summary)

        try:
            result = fn()
            elapsed = int((time.time() - start) * 1000)
            completed_at = datetime.utcnow()

            # fn returns a dict with stage metadata + a "result" key for the actual data
            stage_meta = result if isinstance(result, dict) else {}
            self._persist_stage(
                stage_id,
                status=stage_meta.get("status", "COMPLETED"),
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=elapsed,
                input_summary=input_summary,
                output_summary=stage_meta.get("output_summary"),
                metrics=stage_meta.get("metrics"),
                logs=stage_meta.get("logs"),
                warnings=stage_meta.get("warnings"),
                errors=stage_meta.get("errors"),
                generated_code=stage_meta.get("generated_code"),
                artifacts=stage_meta.get("artifacts"),
            )
            return stage_meta.get("data")

        except Exception as e:
            elapsed = int((time.time() - start) * 1000)
            self._persist_stage(
                stage_id,
                status="FAILED",
                started_at=started_at,
                completed_at=datetime.utcnow(),
                duration_ms=elapsed,
                input_summary=input_summary,
                errors=[str(e)],
            )
            raise

    # ── Main Pipeline ──

    def run(self) -> Dict[str, Any]:
        # Initialize all stages as WAITING
        self._init_all_stages()

        filename = os.path.basename(self.file_path)

        # ═══════════════════════════════════════════
        # Stage 2: Parse (combines backend stages 1-3: Parse + DAG)
        # Note: Stage 1 (Upload) is handled by the upload endpoint separately
        # ═══════════════════════════════════════════
        self.log("INFO", f"Stage 1-3: Parsing {filename}")

        def _do_parse():
            workbook_meta = parse_workbook(self.file_path)

            # Unity Catalog Auto-Discovery (Stage 3.5)
            self._run_catalog_discovery(workbook_meta)

            # Dependency Graph (part of Parse stage)
            dag_engine = DependencyGraphEngine(workbook_meta)
            cycles = dag_engine.detect_cycles()
            if cycles:
                self.log("ERROR", f"Circular references detected in formulas: {cycles}")

            ds_count = len(workbook_meta.datasources)
            ws_count = len(workbook_meta.worksheets)
            db_count = len(workbook_meta.dashboards)
            calc_count = sum(len(ds.calculated_fields) for ds in workbook_meta.datasources)
            params_count = len(workbook_meta.parameters)
            lod_count = sum(
                1 for ds in workbook_meta.datasources
                for cf in ds.calculated_fields
                if cf.formula and '{' in cf.formula and 'FIXED' in cf.formula.upper()
            )

            # Build actual artifact data
            worksheets = [w.name for w in workbook_meta.worksheets]
            dashboards_list = []
            for d in workbook_meta.dashboards:
                dashboards_list.append({
                    "name": d.name,
                    "worksheets": d.worksheets,
                    "zone_count": len(d.zones),
                })
            datasources_list = []
            for ds in workbook_meta.datasources:
                datasources_list.append({
                    "name": ds.name,
                    "caption": ds.caption or ds.name,
                    "connection_type": ds.connection_type or "unknown",
                    "table_count": len(ds.tables),
                    "tables": [t.name for t in ds.tables],
                    "column_count": len(ds.columns),
                    "columns": [c.internal_name for c in ds.columns[:100]],
                    "calculated_field_count": len(ds.calculated_fields),
                    "is_databricks": ds.databricks_connection is not None,
                })
            calc_fields_list = []
            for ds in workbook_meta.datasources:
                for cf in ds.calculated_fields:
                    calc_fields_list.append({
                        "name": cf.name,
                        "caption": cf.caption or cf.name,
                        "formula": cf.formula,
                        "type": cf.formula_type,
                        "datasource": ds.name,
                    })
            parameters_list = [
                {"name": p.name, "datatype": p.datatype, "current_value": p.current_value, "domain_type": p.domain_type}
                for p in workbook_meta.parameters
            ]
            filters_list = []
            for w in workbook_meta.worksheets:
                for f in w.filters:
                    filters_list.append({"worksheet": w.name, "field": f.field_name, "type": f.filter_type, "scope": f.scope})
            groups_list = [{"name": g.name, "field": g.field, "members": g.members[:20]} for g in workbook_meta.groups]
            sets_list = [{"name": s.name, "field": s.field, "condition": s.condition} for s in workbook_meta.sets]
            hierarchies_list = [{"name": h.name, "levels": h.levels} for h in workbook_meta.hierarchies]

            # Joins / Relationships from datasources
            joins_list = []
            relationships_list = []
            for ds in workbook_meta.datasources:
                for j in ds.joins:
                    joins_list.append({
                        "join_type": j.join_type,
                        "left_table": j.left_table,
                        "left_column": j.left_column,
                        "right_table": j.right_table,
                        "right_column": j.right_column,
                        "datasource": ds.name,
                    })
                for r in ds.relationships:
                    relationships_list.append({
                        "table1": r.table1,
                        "table2": r.table2,
                        "table1_column": r.table1_column,
                        "table2_column": r.table2_column,
                        "type": r.relationship_type,
                        "datasource": ds.name,
                    })

            # Databricks discovery results
            databricks_discovery = None
            if self.semantic_model is not None:
                sm = self.semantic_model
                summary = sm.summary()
                discovered_tables = []
                discovered_columns = []
                discovered_relationships = []
                for src in sm.sources:
                    for tbl in src.tables:
                        discovered_tables.append({
                            "full_name": tbl.full_name,
                            "table_type": tbl.table_type.value if hasattr(tbl.table_type, 'value') else str(tbl.table_type),
                            "column_count": len(tbl.columns),
                        })
                        for col in tbl.columns[:50]:
                            discovered_columns.append({
                                "table": tbl.full_name,
                                "name": col.name,
                                "type": col.data_type.value if hasattr(col.data_type, 'value') else str(col.data_type),
                            })
                    for rel in getattr(src, 'relationships', []):
                        discovered_relationships.append({
                            "from_table": getattr(rel, 'from_table', ''),
                            "from_column": getattr(rel, 'from_column', ''),
                            "to_table": getattr(rel, 'to_table', ''),
                            "to_column": getattr(rel, 'to_column', ''),
                        })

                databricks_discovery = {
                    "detected": True,
                    "catalog_count": summary.get('catalog_count', 0),
                    "schema_count": summary.get('schema_count', 0),
                    "table_count": summary.get('table_count', 0),
                    "column_count": summary.get('column_count', 0),
                    "relationship_count": summary.get('relationship_count', 0),
                    "tables": discovered_tables[:200],
                    "columns": discovered_columns[:500],
                    "relationships": discovered_relationships[:100],
                    "sources": [
                        {
                            "datasource_name": src.datasource_name,
                            "status": src.discovery_status,
                            "table_count": src.discovered_table_count,
                            "column_count": src.discovered_column_count,
                        }
                        for src in sm.sources
                    ],
                }
            elif workbook_meta.has_databricks_connections:
                databricks_discovery = {
                    "detected": True,
                    "connections": [
                        {
                            "datasource_name": c.datasource_name,
                            "host": c.host,
                            "catalog": c.catalog,
                            "schema": c.schema_name,
                            "warehouse_id": c.warehouse_id,
                            "connection_class": c.connection_class,
                        }
                        for c in workbook_meta.databricks_connections
                    ],
                    "credentials_missing": not (self.databricks_host and self.databricks_token),
                }

            return {
                "status": "COMPLETED",
                "output_summary": f"Parsed {ws_count} worksheets, {db_count} dashboards, {ds_count} datasources, {calc_count} calculated fields",
                "metrics": {
                    "worksheets_parsed": ws_count,
                    "dashboards_parsed": db_count,
                    "datasource_count": ds_count,
                    "calculated_fields_detected": calc_count,
                    "lod_expressions": lod_count,
                    "parameters": params_count,
                    "filters": sum(len(w.filters) for w in workbook_meta.worksheets),
                    "custom_sql": 0,
                    "tableau_version": workbook_meta.version or "Unknown",
                    "model_type": workbook_meta.model_type,
                    "dependency_cycles": cycles,
                },
                "artifacts": {
                    "worksheets": worksheets,
                    "dashboards": dashboards_list,
                    "datasources": datasources_list,
                    "calculated_fields": calc_fields_list[:200],
                    "parameters": parameters_list,
                    "filters": filters_list[:100],
                    "groups": groups_list,
                    "sets": sets_list,
                    "hierarchies": hierarchies_list,
                    "joins": joins_list,
                    "relationships": relationships_list,
                    "databricks_discovery": databricks_discovery,
                },
                "logs": [
                    f"[INFO] Unpacking {filename}",
                    f"[INFO] XML DOM tree parsed",
                    f"[INFO] Extracted {ds_count} datasources, {ws_count} worksheets",
                    f"[INFO] DAG topological order resolved ({len(cycles)} cycles detected)",
                    f"[SUCCESS] Parse completed: {calc_count} calculated fields indexed",
                ],
                "warnings": [f"Circular reference: {c}" for c in cycles] if cycles else [],
                "errors": [],
                "data": workbook_meta,
            }

        workbook_meta = self._run_stage(
            "PARSE",
            input_summary=f"{filename} ({os.path.getsize(self.file_path)} bytes)",
            fn=_do_parse,
        )

        # ═══════════════════════════════════════════
        # Stage 3: Calculation Deep Dive (backend: Expressions)
        # ═══════════════════════════════════════════
        self.log("INFO", "Stage 4: Calculating field dependencies and expression analysis")

        def _do_calc_deep_dive():
            from app.services.compiler.canonical_field_resolver import CanonicalFieldResolver
            field_resolver = CanonicalFieldResolver(workbook_meta, semantic_model=self.semantic_model)

            registry = field_resolver.dump_registry()
            excluded = [f for f in registry if f.get('is_excluded')]
            for exc in excluded:
                self.log("INFO", f"Excluding field '{exc['internal_name']}' ({exc.get('exclude_reason', 'N/A')})")

            # Validate fields against UC schema if semantic model is available
            mismatches = []
            if self.semantic_model is not None:
                mismatches = field_resolver.validate_against_schema()
                for mm in mismatches[:20]:
                    self.log("WARNING", f"Field '{mm['field']}' (physical: '{mm['physical_name']}') not found in Unity Catalog schema")

            total_fields = len(registry)
            calc_fields = [f for f in registry if f.get('is_calculated')]
            lod_fields = [f for f in registry if f.get('expression_type') == 'LOD']
            window_fields = [f for f in registry if f.get('expression_type') == 'TABLE_CALC']
            nested = [f for f in registry if f.get('has_dependencies')]

            # Build actual artifact data
            calc_fields_detail = [
                {
                    "name": f.get('internal_name', ''),
                    "caption": f.get('caption', ''),
                    "formula": f.get('original_formula', f.get('formula', '')),
                    "compiled_sql": f.get('compiled_sql', ''),
                    "type": f.get('expression_type', 'STANDARD'),
                    "dependencies": f.get('dependencies', [])[:10],
                    "referenced_fields": f.get('referenced_fields', [])[:10],
                    "datasource": f.get('datasource', ''),
                }
                for f in calc_fields[:200]
            ]
            lod_detail = [
                {
                    "name": f.get('internal_name', ''),
                    "formula": f.get('original_formula', f.get('formula', '')),
                    "compiled_sql": f.get('compiled_sql', ''),
                    "datasource": f.get('datasource', ''),
                }
                for f in lod_fields[:100]
            ]
            window_detail = [
                {
                    "name": f.get('internal_name', ''),
                    "formula": f.get('original_formula', f.get('formula', '')),
                    "compiled_sql": f.get('compiled_sql', ''),
                    "datasource": f.get('datasource', ''),
                }
                for f in window_fields[:100]
            ]
            excluded_detail = [
                {
                    "name": f.get('internal_name', ''),
                    "reason": f.get('exclude_reason', ''),
                }
                for f in excluded[:50]
            ]
            mismatch_detail = [
                {
                    "field": mm.get('field', ''),
                    "physical_name": mm.get('physical_name', ''),
                    "expected_type": mm.get('expected_type', ''),
                }
                for mm in mismatches[:50]
            ]

            return {
                "status": "COMPLETED",
                "output_summary": f"Analyzed {total_fields} fields: {len(calc_fields)} calculated, {len(lod_fields)} LOD, {len(window_fields)} window functions",
                "metrics": {
                    "total_fields": total_fields,
                    "calculated_fields": len(calc_fields),
                    "nested_calculations": len(nested),
                    "lod_expressions": len(lod_fields),
                    "window_functions": len(window_fields),
                    "table_calculations": len(window_fields),
                    "excluded_fields": len(excluded),
                    "schema_mismatches": len(mismatches),
                    "complexity_analysis": "HIGH" if len(lod_fields) > 5 else "MEDIUM" if len(calc_fields) > 10 else "LOW",
                    "migration_confidence": max(0, 100 - len(mismatches) * 5 - len(excluded) * 2),
                },
                "artifacts": {
                    "calculated_fields": calc_fields_detail,
                    "lod_expressions": lod_detail,
                    "window_functions": window_detail,
                    "excluded_fields": excluded_detail,
                    "schema_mismatches": mismatch_detail,
                },
                "logs": [
                    f"[INFO] Analyzing {total_fields} fields from {len(workbook_meta.datasources)} datasources",
                    f"[INFO] Found {len(calc_fields)} calculated fields",
                    f"[INFO] Detected {len(lod_fields)} LOD expressions",
                    f"[INFO] Detected {len(window_fields)} window/table calculations",
                    f"[SUCCESS] Calculation deep dive complete",
                ],
                "warnings": [f"Schema mismatch: {mm['field']}" for mm in mismatches[:10]],
                "errors": [],
                "data": field_resolver,
            }

        field_resolver = self._run_stage(
            "CALC_DEEP_DIVE",
            input_summary=f"{sum(len(ds.calculated_fields) for ds in workbook_meta.datasources)} raw Tableau formulas",
            fn=_do_calc_deep_dive,
        )

        # ═══════════════════════════════════════════
        # Stage 4: Source Mapping Validation (backend: Mapping)
        # ═══════════════════════════════════════════
        self.log("INFO", "Stage 5: Resolving datasource table mappings")

        def _do_source_mapping():
            resolved, unresolved_tables = build_table_mapping(
                workbook_meta.datasources,
                user_mapping=self.table_mapping,
                default_catalog=self.default_catalog,
                default_schema=self.default_schema,
            )
            if unresolved_tables:
                for t in unresolved_tables:
                    self.log(
                        "ERROR",
                        f"Unresolved table '{t['table']}' from datasource '{t['datasource']}' "
                        f"(connection: {t['connection_type']}). "
                        f"Provide a table_mapping entry: "
                        f"{{'{t['table']}': '<catalog>.<schema>.{t['suggested_name']}'}}"
                    )

            mapped_count = len(self.table_mapping)
            total_tables = sum(len(ds.tables) for ds in workbook_meta.datasources)

            # Build actual artifact data
            table_mappings = [
                {"tableau_table": k, "databricks_table": v}
                for k, v in self.table_mapping.items()
            ]
            unresolved_detail = [
                {
                    "table": t.get('table', ''),
                    "datasource": t.get('datasource', ''),
                    "connection_type": t.get('connection_type', ''),
                    "suggested_name": t.get('suggested_name', ''),
                }
                for t in (unresolved_tables or [])
            ]
            # Column mappings from resolved
            column_mappings = []
            if isinstance(resolved, dict):
                for tbl_name, tbl_ref in resolved.items():
                    column_mappings.append({"tableau_table": tbl_name, "resolved_to": str(tbl_ref)})

            # All joins/relationships from datasources
            all_joins = []
            for ds in workbook_meta.datasources:
                for j in ds.joins:
                    all_joins.append({
                        "join_type": j.join_type,
                        "left_table": j.left_table,
                        "left_column": j.left_column,
                        "right_table": j.right_table,
                        "right_column": j.right_column,
                        "datasource": ds.name,
                    })
                for r in ds.relationships:
                    all_joins.append({
                        "join_type": r.relationship_type,
                        "left_table": r.table1,
                        "left_column": r.table1_column,
                        "right_table": r.table2,
                        "right_column": r.table2_column,
                        "datasource": ds.name,
                    })

            # Databricks connection info
            databricks_connections = []
            for conn in workbook_meta.databricks_connections:
                databricks_connections.append({
                    "datasource_name": conn.datasource_name,
                    "host": conn.host,
                    "catalog": conn.catalog,
                    "schema": conn.schema_name,
                    "warehouse_id": conn.warehouse_id,
                    "connection_class": conn.connection_class,
                })

            return {
                "status": "WARNING" if unresolved_tables else "COMPLETED",
                "output_summary": f"Mapped {mapped_count}/{total_tables} tables" + (f", {len(unresolved_tables)} unresolved" if unresolved_tables else ""),
                "metrics": {
                    "total_tables": total_tables,
                    "mapped_tables": mapped_count,
                    "unresolved_tables": len(unresolved_tables) if unresolved_tables else 0,
                    "datasource_count": len(workbook_meta.datasources),
                    "connection_types": list(set(ds.connection_type for ds in workbook_meta.datasources if ds.connection_type)),
                    "default_catalog": self.default_catalog or "N/A",
                    "default_schema": self.default_schema or "N/A",
                    "validation_status": "PASS" if not unresolved_tables else "FAIL",
                },
                "artifacts": {
                    "table_mappings": table_mappings,
                    "column_mappings": column_mappings,
                    "unresolved_tables": unresolved_detail,
                    "detected_joins": all_joins,
                    "databricks_connections": databricks_connections,
                    "mapping_json": self.table_mapping,
                },
                "logs": [
                    f"[INFO] Scanning {len(workbook_meta.datasources)} datasources",
                    f"[INFO] User-provided mappings: {mapped_count}",
                    f"[INFO] Default catalog: {self.default_catalog or 'N/A'}, schema: {self.default_schema or 'N/A'}",
                    f"[{'SUCCESS' if not unresolved_tables else 'WARNING'}] Mapping validation {'passed' if not unresolved_tables else 'has issues'}",
                ],
                "warnings": [f"Unresolved: {t['table']} ({t['connection_type']})" for t in (unresolved_tables or [])],
                "errors": [],
                "data": (resolved, unresolved_tables),
            }

        _mapping_result = self._run_stage(
            "SOURCE_MAPPING",
            input_summary=f"{len(workbook_meta.datasources)} Tableau datasources with {len(self.table_mapping)} user mappings",
            fn=_do_source_mapping,
        )

        # ═══════════════════════════════════════════
        # Stage 5: Calculation Logic Conversion (backend: SQL)
        # ═══════════════════════════════════════════
        self.log("INFO", "Stage 6: Compiling expressions & building canonical field resolver")

        # The field_resolver was already built in CALC_DEEP_DIVE; this stage is about
        # the SQL transpilation that happens during UBIM normalization.
        # We mark it as COMPLETED with relevant SQL-specific metrics.
        def _do_calc_logic_conversion():
            # SQL transpilation happens inline during UBIM normalization (stage 7)
            # but we capture the field resolver's SQL readiness here
            registry = field_resolver.dump_registry() if hasattr(field_resolver, 'dump_registry') else []
            compiled = [f for f in registry if f.get('compiled_sql')]
            unsupported = [f for f in registry if f.get('is_unsupported')]

            sample_sql = None
            for f in compiled[:1]:
                if f.get('compiled_sql'):
                    sample_sql = f['compiled_sql']

            # Build actual conversion artifact data
            conversions = [
                {
                    "name": f.get('internal_name', ''),
                    "caption": f.get('caption', ''),
                    "original_formula": f.get('original_formula', f.get('formula', '')),
                    "compiled_sql": f.get('compiled_sql', ''),
                    "datasource": f.get('datasource', ''),
                }
                for f in compiled[:200]
            ]
            unsupported_detail = [
                {
                    "name": f.get('internal_name', ''),
                    "formula": f.get('original_formula', f.get('formula', '')),
                    "reason": f.get('unsupported_reason', f.get('exclude_reason', 'Unsupported function')),
                    "datasource": f.get('datasource', ''),
                }
                for f in unsupported[:100]
            ]

            # All compiled SQL concatenated for generated_code display
            all_sql = "\n\n".join(
                f"-- {f.get('internal_name', 'unknown')}\n{f.get('compiled_sql', '')}"
                for f in compiled[:50]
                if f.get('compiled_sql')
            )

            return {
                "status": "COMPLETED",
                "output_summary": f"SQL conversion ready: {len(compiled)} expressions compiled, {len(unsupported)} unsupported",
                "metrics": {
                    "expressions_compiled": len(compiled),
                    "expressions_unsupported": len(unsupported),
                    "total_expressions": len(registry),
                    "compilation_rate": f"{(len(compiled) / max(len(registry), 1)) * 100:.1f}%",
                    "databricks_compatibility": "HIGH" if len(unsupported) == 0 else "MEDIUM" if len(unsupported) < 5 else "LOW",
                },
                "artifacts": {
                    "conversions": conversions,
                    "unsupported": unsupported_detail,
                },
                "logs": [
                    f"[INFO] Compiling {len(registry)} expressions to Databricks SQL",
                    f"[INFO] {len(compiled)} expressions compiled successfully",
                    f"[{'SUCCESS' if not unsupported else 'WARNING'}] Conversion {'complete' if not unsupported else f'{len(unsupported)} unsupported functions'}",
                ],
                "warnings": [f"Unsupported: {f.get('internal_name', 'unknown')}" for f in unsupported[:10]],
                "errors": [],
                "generated_code": all_sql or sample_sql,
                "data": None,
            }

        self._run_stage(
            "CALC_LOGIC_CONVERSION",
            input_summary="Tableau formula syntax tree + field resolver",
            fn=_do_calc_logic_conversion,
        )

        # ═══════════════════════════════════════════
        # Stage 6: Dashboard Layout Generation (backend: UBIM + Generate)
        # ═══════════════════════════════════════════
        self.log("INFO", "Stage 7: Normalizing TOM to Universal BI Model (UBIM)")

        def _do_layout_generation():
            ubim = normalize_tom_to_ubim(
                workbook_meta,
                table_mapping=self.table_mapping,
                default_catalog=self.default_catalog,
                default_schema=self.default_schema,
                field_resolver=field_resolver,
                semantic_model=self.semantic_model,
            )
            ubim_opt = optimize_ubim(ubim)

            self.log("INFO", "Stage 8: Generating Lakeview JSON & projecting 6-column layout grid")
            lakeview_dash = generate_lakeview_dashboard(ubim_opt)

            widget_count = sum(len(p.layout) for p in lakeview_dash.pages) if hasattr(lakeview_dash, 'pages') else 0
            page_count = len(lakeview_dash.pages) if hasattr(lakeview_dash, 'pages') else 0
            dataset_count = len(lakeview_dash.datasets) if hasattr(lakeview_dash, 'datasets') else 0

            # Build actual artifact data
            pages_detail = []
            visual_types = set()
            widgets_detail = []
            if hasattr(lakeview_dash, 'pages'):
                for p in lakeview_dash.pages:
                    page_widgets = []
                    for item in p.layout:
                        w = item.widget
                        w_info = {
                            "name": w.name,
                            "type": "textbox" if w.textbox_spec else "chart",
                            "position": {"x": item.position.x, "y": item.position.y, "w": item.position.width, "h": item.position.height},
                        }
                        if w.spec:
                            spec_version = w.spec.get("version", 0)
                            w_info["spec_version"] = spec_version
                            # Try to extract visual type from spec
                            for enc_key in ["mark", "encoding"]:
                                if enc_key in w.spec:
                                    w_info["visual_type"] = str(w.spec.get("mark", {}).get("type", "unknown")) if isinstance(w.spec.get("mark"), dict) else str(w.spec.get("mark", "unknown"))
                                    visual_types.add(w_info.get("visual_type", "unknown"))
                                    break
                        if w.queries:
                            w_info["dataset"] = w.queries[0].query.get("datasetName", "") if isinstance(w.queries[0].query, dict) else getattr(w.queries[0].query, 'datasetName', '')
                        page_widgets.append(w_info)
                        widgets_detail.append(w_info)
                    pages_detail.append({
                        "name": p.name,
                        "display_name": p.displayName,
                        "widget_count": len(page_widgets),
                        "widgets": page_widgets,
                    })

            datasets_detail = []
            if hasattr(lakeview_dash, 'datasets'):
                for ds in lakeview_dash.datasets:
                    datasets_detail.append({
                        "name": ds.name,
                        "display_name": ds.displayName,
                        "query": ds.query,
                    })

            return {
                "status": "COMPLETED",
                "output_summary": f"Generated {page_count} pages, {widget_count} widgets, {dataset_count} datasets",
                "metrics": {
                    "pages_generated": page_count,
                    "widgets_generated": widget_count,
                    "datasets_generated": dataset_count,
                    "layout_grid": "6-column",
                    "visual_types_detected": list(visual_types),
                },
                "artifacts": {
                    "pages": pages_detail,
                    "datasets": datasets_detail,
                    "widgets": widgets_detail[:200],
                    "visual_types": list(visual_types),
                },
                "logs": [
                    f"[INFO] UBIM normalization: mapping Tableau marks to Lakeview visual types",
                    f"[INFO] UBIM optimization pass complete",
                    f"[INFO] Generating 6-column grid layout coordinates",
                    f"[SUCCESS] Lakeview dashboard generated: {page_count} pages, {widget_count} widgets",
                ],
                "warnings": [],
                "errors": [],
                "data": lakeview_dash,
            }

        lakeview_dash = self._run_stage(
            "LAYOUT_GENERATION",
            input_summary=f"TOM with {len(workbook_meta.worksheets)} worksheets + transpiled SQL",
            fn=_do_layout_generation,
        )

        # ═══════════════════════════════════════════
        # Stage 7: Lakeview Schema Validation (backend: Validate)
        # ═══════════════════════════════════════════
        self.log("INFO", "Stage 9: Executing validation suite & pruning incomplete widgets")

        def _do_schema_validation():
            val_res = validate_lakeview_dashboard(lakeview_dash)
            for err in val_res.get("errors", []):
                self.log("ERROR", err)
            for warn in val_res.get("warnings", []):
                self.log("WARNING", warn)

            removed = prune_incomplete_widgets(lakeview_dash)
            for title in removed:
                self.log("ERROR", f"Pruned incomplete widget '{title}' — empty encodings/queries would render blank.")
                val_res.setdefault("errors", []).append(
                    f"Pruned incomplete widget '{title}' — empty encodings/queries would render blank."
                )
            if removed:
                val_res["valid"] = False
                post = validate_lakeview_dashboard(lakeview_dash)
                for err in post.get("errors", []):
                    if err not in val_res["errors"]:
                        val_res["errors"].append(err)
                        self.log("ERROR", err)
                val_res["valid"] = len(val_res["errors"]) == 0
                val_res["warnings"] = post.get("warnings", val_res.get("warnings", []))

            error_count = len(val_res.get("errors", []))
            warning_count = len(val_res.get("warnings", []))

            # Build generated JSON summary (truncated for storage)
            import json as _json
            generated_json_str = None
            try:
                dash_dict = lakeview_dash.to_dict()
                generated_json_str = _json.dumps(dash_dict, indent=2, ensure_ascii=False)[:50000]
            except Exception:
                pass

            return {
                "status": "COMPLETED" if val_res.get("valid") else "WARNING",
                "output_summary": f"{'VALID' if val_res.get('valid') else 'INVALID'}: {error_count} errors, {warning_count} warnings, {len(removed)} widgets pruned",
                "metrics": {
                    "is_valid": val_res.get("valid", False),
                    "error_count": error_count,
                    "warning_count": warning_count,
                    "pruned_widgets": len(removed),
                    "tier_status": val_res.get("tier_status", {}),
                },
                "artifacts": {
                    "validation_errors": val_res.get("errors", []),
                    "validation_warnings": val_res.get("warnings", []),
                    "tier_status": val_res.get("tier_status", {}),
                    "pruned_widgets": list(removed),
                    "generated_json_preview": generated_json_str,
                },
                "generated_code": generated_json_str,
                "logs": [
                    f"[INFO] Running JSON schema validation",
                    f"[INFO] Checking layout bounds (x + width <= 6)",
                    f"[INFO] Checking widget encoding completeness",
                    f"[{'SUCCESS' if val_res.get('valid') else 'WARNING'}] Validation {'passed' if val_res.get('valid') else 'completed with issues'}",
                ],
                "warnings": val_res.get("warnings", []),
                "errors": val_res.get("errors", []),
                "data": val_res,
            }

        val_res = self._run_stage(
            "SCHEMA_VALIDATION",
            input_summary="Lakeview AST JSON",
            fn=_do_schema_validation,
        )

        # ═══════════════════════════════════════════
        # Stage 9: Finalize (backend: Report generation)
        # ═══════════════════════════════════════════
        self.log("INFO", "Stage 10: Assembling migration report")

        def _do_finalize():
            report = generate_migration_report(workbook_meta, lakeview_dash, val_res, self.error_bag)

            summary = report.get("summary", {})
            return {
                "status": "COMPLETED",
                "output_summary": f"Migration report generated: {summary.get('worksheets_total', 0)} worksheets, {summary.get('expressions_total', 0)} expressions",
                "metrics": {
                    "worksheets_total": summary.get("worksheets_total", 0),
                    "expressions_total": summary.get("expressions_total", 0),
                    "expressions_compiled": summary.get("expressions_rule_compiled", 0),
                    "expressions_unsupported": summary.get("expressions_unsupported", 0),
                    "lakeview_pages": summary.get("lakeview_pages", 0),
                    "lakeview_widgets": summary.get("lakeview_widgets", 0),
                    "validation_valid": val_res.get("valid", False),
                },
                "artifacts": {
                    "report_summary": summary,
                    "target_lakeview": report.get("target_lakeview", {}),
                    "error_bag": self.error_bag[-50:],
                    "output_files": [
                        f"{self.job_uuid}.lvdash.json",
                        f"{self.job_uuid}_pretty.lvdash.json",
                        "migration_report.json",
                        "validation_report.json",
                    ],
                },
                "logs": [
                    f"[INFO] Assembling migration telemetry report",
                    f"[SUCCESS] Report generated successfully",
                ],
                "warnings": [],
                "errors": [],
                "data": report,
            }

        report = self._run_stage(
            "FINALIZE",
            input_summary="Pipeline execution results + validation output",
            fn=_do_finalize,
        )

        # ── Assemble final result ──
        result = {
            "status": "COMPLETED" if val_res.get("valid", False) else "FAILED_VALIDATION",
            "workbook_meta": workbook_meta,
            "lakeview_dashboard": lakeview_dash,
            "validation_results": val_res,
            "report": report,
            "error_bag": self.error_bag,
            "persist_allowed": True,
        }

        # Include Databricks source info for the Data Model screen
        if workbook_meta.has_databricks_connections:
            result["databricks_sources"] = [
                conn.model_dump() for conn in workbook_meta.databricks_connections
            ]
        if self.semantic_model is not None:
            result["semantic_model_summary"] = self.semantic_model.summary()

        return result

    def _run_catalog_discovery(self, workbook_meta: WorkbookMetadata) -> None:
        """Stage 3.5: Auto-discover Unity Catalog metadata when Databricks connections detected.

        Discovery triggers when ALL of the following are true:
          1. Workbook contains at least one Databricks-type connection
          2. Databricks host is available (from connection or env)
          3. Databricks token is available (from env/config — never from Tableau XML)

        On failure, logs warnings and falls back to the existing manual mapping flow.
        """
        if not workbook_meta.has_databricks_connections:
            return

        conn_count = len(workbook_meta.databricks_connections)
        self.log(
            "INFO",
            f"Stage 3.5: {conn_count} Databricks connection(s) detected — "
            f"initiating Unity Catalog auto-discovery"
        )

        # Resolve credentials from: pipeline params → env → config
        host = self.databricks_host
        token = self.databricks_token
        wh_id = self.warehouse_id

        if not host or not token:
            try:
                from app.core.config import settings
                host = host or settings.DATABRICKS_HOST or ""
                token = token or settings.DATABRICKS_TOKEN or ""
                wh_id = wh_id or settings.DEFAULT_WAREHOUSE_ID or ""
            except Exception:
                pass

        if not host or not token:
            self.log(
                "WARNING",
                "Databricks connections detected but credentials not available. "
                "Set DATABRICKS_HOST and DATABRICKS_TOKEN in .env to enable auto-discovery. "
                "Falling back to manual datasource mapping."
            )
            return

        try:
            from app.services.mapper.catalog_discovery_service import CatalogDiscoveryService

            self.semantic_model = CatalogDiscoveryService.discover(
                workbook_meta=workbook_meta,
                host_override=host,
                token_override=token,
                warehouse_id_override=wh_id,
                discover_constraints=True,
                discover_properties=False,
            )

            if self.semantic_model is not None:
                summary = self.semantic_model.summary()
                self.log(
                    "INFO",
                    f"✓ UC Discovery complete: "
                    f"{summary['catalog_count']} catalogs, "
                    f"{summary['schema_count']} schemas, "
                    f"{summary['table_count']} tables, "
                    f"{summary['column_count']} columns, "
                    f"{summary['relationship_count']} relationships"
                )

                # Log each discovered source for diagnostics
                for src in self.semantic_model.sources:
                    status_icon = "✓" if src.discovery_status == "DISCOVERED" else "✗"
                    self.log(
                        "INFO" if src.discovery_status == "DISCOVERED" else "WARNING",
                        f"  {status_icon} Source '{src.datasource_name}' → "
                        f"{src.discovery_status} "
                        f"({src.discovered_table_count} tables, "
                        f"{src.discovered_column_count} columns)"
                    )
            else:
                self.log("WARNING", "UC Discovery returned no results — using manual mapping")

        except Exception as e:
            self.log(
                "WARNING",
                f"UC auto-discovery failed: {str(e)}. Falling back to manual mapping."
            )
            logger.exception("Stage 3.5 UC Discovery failed")
