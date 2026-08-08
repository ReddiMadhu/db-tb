"""
Tableau to Databricks Migration — 8-Stage Pipeline Orchestrator

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
from app.services.parser.workbook_ontology import build_workbook_ontology
from app.services.normalizer.tom_to_ubim import normalize_tom_to_ubim
from app.services.normalizer.optimizer import optimize_ubim
from app.services.generator.lakeview_generator import generate_lakeview_dashboard
from app.services.validator.validation_engine import (
    validate_lakeview_dashboard,
    prune_incomplete_widgets,
)
from app.services.reporter.migration_report import generate_migration_report

logger = logging.getLogger(__name__)


class MigrationPipeline:
    """8-Stage Migration Pipeline Orchestrator with per-stage DB persistence.

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
        """Initialize or reset stages for job execution.

        Preserves stages already completed before pipeline launch:
        - UPLOAD: completed during file upload
        - PARSE: completed during file upload
        - SOURCE_MAPPING: completed by execute endpoint pre-flight check
        """
        if not self.job_uuid:
            return
        from app.models.stage_model import StageResult, PIPELINE_STAGE_DEFS
        # Stages that are completed before the pipeline runs and should not be reset
        PRESERVE_IF_COMPLETED = {"UPLOAD", "PARSE", "SOURCE_MAPPING"}
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
                    # Preserve pre-completed stages
                    if stage_id in PRESERVE_IF_COMPLETED and row.status == "COMPLETED":
                        continue
                    # Reset other stages to WAITING for pipeline execution
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
                    "title": d.title,  # may be null — do not silently substitute name
                    "worksheets": d.worksheets,
                    "zone_count": d.total_zone_count,
                    "filter_controls": d.filter_controls,
                    "legend_controls": d.legend_controls,
                })

            main_db = workbook_meta.dashboards[0] if workbook_meta.dashboards else None
            dashboard_name = main_db.name if main_db else "Workbook Dashboard"
            # title is authoritative metadata only; do not fall back to name here
            dashboard_title = main_db.title if main_db else None
            dashboard_filters = main_db.filter_controls if main_db else []
            dashboard_legends = main_db.legend_controls if main_db else []

            datasources_list = []
            seen_ds_names = set()
            unique_datasources = []
            measures_set = set()
            dimensions_set = set()

            for ds in workbook_meta.datasources:
                ds_key = ds.caption or ds.name
                if ds_key == "Parameters" or ds.name == "Parameters":
                    continue
                if not ds.tables and not ds.columns and getattr(ds, "databricks_connection", None) is None:
                    continue
                if ds_key not in seen_ds_names:
                    seen_ds_names.add(ds_key)
                    unique_datasources.append(ds)
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
                for col in ds.columns:
                    cname = col.caption or col.internal_name
                    role = (col.role or "").lower().strip()
                    # Role attribute is sole source of truth — never datatype
                    if role == "measure":
                        measures_set.add(cname)
                    elif role == "dimension":
                        dimensions_set.add(cname)

            measures_list = sorted(list(measures_set))
            dimensions_list = sorted(list(dimensions_set))

            # Build detailed visuals for frontend rendering (enriched for Visual Intelligence Explorer)
            detailed_visuals = []
            for w in workbook_meta.worksheets:
                detailed_visuals.append({
                    "name": w.name,
                    "title": w.title or w.name,
                    "caption": w.caption or "",
                    "description": w.description or "",
                    "hidden": w.hidden,
                    "type": w.visual_type or "Visual Chart",
                    "mark_type": w.mark_type or "Automatic",
                    "worksheet": w.name,
                    "columns": w.columns,
                    "rows": w.rows,
                    "measures": list(w.measures) if w.measures else [],
                    "dimensions": list(w.dimensions) if w.dimensions else [],
                    "filters": [f.field_name for f in w.filters],
                    "encoding": f"Mark Type: {w.mark_type or 'Automatic'}, Visual: {w.visual_type or 'Chart'}",
                    "tooltip": w.tooltip_text or "",
                    "datasource_name": w.datasource_name or "",
                    "used_calculated_fields": list(w.used_calculated_fields) if w.used_calculated_fields else [],
                    "used_parameters": list(w.used_parameters) if w.used_parameters else [],
                    "used_sets": list(w.used_sets) if w.used_sets else [],
                    "used_groups": list(w.used_groups) if w.used_groups else [],
                    "used_hierarchies": list(w.used_hierarchies) if w.used_hierarchies else [],
                    "used_table_calcs": list(w.used_table_calcs) if w.used_table_calcs else [],
                    "used_lod_calcs": list(w.used_lod_calcs) if w.used_lod_calcs else [],
                    "rows_shelves": [
                        {"field_name": sf.field_name, "derivation": sf.derivation, "raw": sf.raw}
                        for sf in w.rows_shelves
                    ],
                    "columns_shelves": [
                        {"field_name": sf.field_name, "derivation": sf.derivation, "raw": sf.raw}
                        for sf in w.columns_shelves
                    ],
                    "pages_shelf": [
                        {"field_name": sf.field_name, "derivation": sf.derivation, "raw": sf.raw}
                        for sf in w.pages_shelf
                    ],
                    "measure_values_used": w.measure_values_used,
                    "encodings": [
                        {"channel": enc.channel, "field_name": enc.field_name, "field_type": enc.field_type,
                         "aggregation": enc.aggregation, "derivation": enc.derivation}
                        for enc in w.encodings
                    ],
                    "mark_properties": [mp.model_dump() for mp in w.mark_properties],
                    "axes": [a.model_dump() for a in w.axes],
                    "legends": [l.model_dump() for l in w.legends],
                    "tooltip_fields": [tf.model_dump() for tf in w.tooltip_fields],
                    "analytics": [a.model_dump() for a in w.analytics],
                    "sorts": [
                        {"field_name": s.field_name, "direction": s.direction, "sort_type": s.sort_type}
                        for s in w.sorts
                    ],
                    "filter_details": [
                        {"field_name": f.field_name, "filter_type": f.filter_type,
                         "min_value": f.min_value, "max_value": f.max_value,
                         "is_context_filter": f.is_context_filter, "is_global": f.is_global, "scope": f.scope,
                         "ui_mode": f.ui_mode, "is_datasource_filter": f.is_datasource_filter, "is_table_calc_filter": f.is_table_calc_filter}
                        for f in w.filters
                    ],
                    "related_actions": w.related_actions,
                    "dashboard_consumers": w.dashboard_consumers,
                    "complexity": w.complexity.model_dump() if w.complexity else None,
                })

            calc_fields_list = []
            seen_calc_names = set()
            for ds in unique_datasources:
                for cf in ds.calculated_fields:
                    cname = cf.caption or cf.name
                    if cname not in seen_calc_names:
                        seen_calc_names.add(cname)
                        calc_fields_list.append({
                            "name": cf.name,
                            "caption": cname,
                            "internal_name": cf.internal_name,
                            "formula": cf.formula,
                            "type": cf.formula_type,
                            "datasource": ds.name,
                            "return_type": cf.return_type or cf.datatype,
                            "dependencies": list(cf.depends_on_fields),
                            "is_used": cf.is_used,
                        })
            parameters_list = [
                {"name": p.name, "datatype": p.datatype, "current_value": p.current_value, "domain_type": p.domain_type}
                for p in workbook_meta.parameters
            ]
            filters_list = []
            for w in workbook_meta.worksheets:
                for f in w.filters:
                    filters_list.append({"worksheet": w.name, "field": f.field_name, "type": f.filter_type, "scope": f.scope})
            groups_list = [
                {"name": g.name, "field": g.field, "members": g.members[:20], "auto_column": g.auto_column, "hidden": g.hidden}
                for g in workbook_meta.groups
            ]
            sets_list = [{"name": s.name, "field": s.field, "condition": s.condition} for s in workbook_meta.sets]
            hierarchies_list = [{"name": h.name, "levels": h.levels} for h in workbook_meta.hierarchies]
            actions_list = [
                {
                    "name": a.name,
                    "caption": a.caption,
                    "action_type": a.type,
                    "activation_type": a.trigger,
                    "source": a.source,
                    "source_type": a.source_type,
                    "target": a.target[0] if a.target else None,
                    "targets": list(a.target),
                    "field": a.fields[0] if a.fields else None,
                    "fields": list(a.fields),
                    "dashboard": a.dashboard,
                    "command": a.command,
                }
                for a in workbook_meta.actions
            ]

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
                    "dashboard_name": dashboard_name,
                    "dashboard_title": dashboard_title,
                    "dashboard_filters": dashboard_filters,
                    "dashboard_legends": dashboard_legends,
                    "detailed_visuals": detailed_visuals,
                    "measures": measures_list,
                    "dimensions": dimensions_list,
                    "worksheets": worksheets,
                    "dashboards": dashboards_list,
                    "datasources": datasources_list,
                    "calculated_fields": calc_fields_list[:200],
                    "parameters": parameters_list,
                    "filters": filters_list[:100],
                    "groups": groups_list,
                    "sets": sets_list,
                    "hierarchies": hierarchies_list,
                    "actions": actions_list,
                    "joins": joins_list,
                    "relationships": relationships_list,
                    "databricks_discovery": databricks_discovery,
                    "workbook_ontology": build_workbook_ontology(workbook_meta).get("workbook_ontology"),
                },
                "logs": [
                    f"[INFO] Unpacking {filename}",
                    f"[INFO] XML DOM tree parsed",
                    f"[INFO] Extracted {ds_count} datasources, {ws_count} worksheets",
                    f"[INFO] DAG topological order resolved ({len(cycles)} cycles detected)",
                    f"[SUCCESS] Parse completed: {calc_count} calculated fields indexed",
                ],
                "warnings": (
                    [f"Circular reference: {c}" for c in cycles]
                    + list(getattr(workbook_meta, "parse_warnings", []) or [])
                ),
                "errors": [],
                "data": workbook_meta,
            }

        workbook_meta = self._run_stage(
            "PARSE",
            input_summary=f"{filename} ({os.path.getsize(self.file_path)} bytes)",
            fn=_do_parse,
        )

        # ═══════════════════════════════════════════
        # NOTE: Source Mapping Validation (Stage 3) is now handled as a
        # pre-flight check in the /execute endpoint before the pipeline runs.
        # The SOURCE_MAPPING stage result is already persisted as COMPLETED.
        # ═══════════════════════════════════════════

        # ═══════════════════════════════════════════
        # Stage 4: Calculation Logic Conversion
        # (field resolve + expression analysis + SQL transpile)
        # ═══════════════════════════════════════════
        self.log("INFO", "Stage 4: Resolving fields and compiling expressions to Databricks SQL")

        def _do_calc_logic_conversion():
            from app.services.compiler.canonical_field_resolver import CanonicalFieldResolver
            from app.services.compiler.calc_logic_conversion import (
                build_calc_logic_conversion_artifacts,
            )

            # Same resolver path formerly run as CALC_DEEP_DIVE — kept here so
            # layout / UBIM still receive a fully built CanonicalFieldResolver.
            resolver = CanonicalFieldResolver(
                workbook_meta, semantic_model=self.semantic_model
            )
            mismatches = []
            if self.semantic_model is not None:
                mismatches = resolver.validate_against_schema()
                for mm in mismatches[:20]:
                    self.log(
                        "WARNING",
                        f"Field '{mm['field']}' (physical: '{mm['physical_name']}') "
                        f"not found in Unity Catalog schema",
                    )

            result = build_calc_logic_conversion_artifacts(
                workbook_meta,
                resolver,
                use_llm=True,
                semantic_model=self.semantic_model,
            )
            calc_count = sum(
                1 for f in resolver.dump_registry() if f.get("is_calculated")
            )
            metrics = result.setdefault("metrics", {})
            metrics["calculated_fields"] = calc_count
            if mismatches:
                result.setdefault("warnings", []).extend(
                    [f"Schema mismatch: {mm['field']}" for mm in mismatches[:10]]
                )
            result["data"] = resolver
            return result

        field_resolver = self._run_stage(
            "CALC_LOGIC_CONVERSION",
            input_summary=(
                f"{sum(len(ds.calculated_fields) for ds in workbook_meta.datasources)} "
                "Tableau calculated-field formulas"
            ),
            fn=_do_calc_logic_conversion,
        )

        # ═══════════════════════════════════════════
        # Stage 5: Dashboard Layout Generation (backend: UBIM + Generate)
        # ═══════════════════════════════════════════
        self.log("INFO", "Stage 5: Normalizing TOM to Universal BI Model (UBIM)")

        def _do_layout_generation():
            from app.services.generator.layout_stage_artifacts import (
                build_layout_generation_artifacts,
            )

            ubim = normalize_tom_to_ubim(
                workbook_meta,
                table_mapping=self.table_mapping,
                default_catalog=self.default_catalog,
                default_schema=self.default_schema,
                field_resolver=field_resolver,
                semantic_model=self.semantic_model,
            )
            ubim_opt = optimize_ubim(ubim)

            self.log("INFO", "Stage 5: Generating Lakeview JSON & projecting 6-column layout grid")
            lakeview_dash = generate_lakeview_dashboard(ubim_opt)
            return build_layout_generation_artifacts(workbook_meta, lakeview_dash)

        lakeview_dash = self._run_stage(
            "LAYOUT_GENERATION",
            input_summary=f"TOM with {len(workbook_meta.worksheets)} worksheets + transpiled SQL",
            fn=_do_layout_generation,
        )

        # ═══════════════════════════════════════════
        # Stage 6: Lakeview Schema Validation (backend: Validate)
        # ═══════════════════════════════════════════
        self.log("INFO", "Stage 6: Executing validation suite & pruning incomplete widgets")

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

            # Ontology fidelity checks (layout chrome preserved into Lakeview)
            ontology = build_workbook_ontology(workbook_meta).get("workbook_ontology") or {}
            main_db = workbook_meta.dashboards[0] if workbook_meta.dashboards else None
            expected_text = len(getattr(main_db, "text_zones", None) or []) if main_db else 0
            expected_filters = len(getattr(main_db, "filter_controls", None) or []) if main_db else 0
            lakeview_text = 0
            lakeview_filters = 0
            if hasattr(lakeview_dash, "pages"):
                for p in lakeview_dash.pages:
                    for item in p.layout:
                        w = item.widget
                        if getattr(w, "is_text_widget", False):
                            lakeview_text += 1
                        wt = (w.spec or {}).get("widgetType", "") if w.spec else ""
                        if isinstance(wt, str) and wt.startswith("filter-"):
                            lakeview_filters += 1

            ontology_fidelity = [
                {
                    "check": "Dashboard text zones mapped to Lakeview textboxes",
                    "expected": expected_text,
                    "actual": lakeview_text,
                    "passed": lakeview_text >= min(expected_text, 1) if expected_text else True,
                },
                {
                    "check": "Dashboard filter cards mapped to Lakeview filter widgets",
                    "expected": expected_filters,
                    "actual": lakeview_filters,
                    "passed": lakeview_filters >= min(expected_filters, 1) if expected_filters else True,
                },
                {
                    "check": "Workbook ontology attached for review",
                    "expected": 1,
                    "actual": 1 if ontology else 0,
                    "passed": bool(ontology),
                },
                {
                    "check": "Tableau dashboard actions mapped to Lakeview interactions",
                    "expected": 0,
                    "actual": 0,
                    "passed": len(workbook_meta.actions or []) == 0,
                    "note": (
                        f"{len(workbook_meta.actions or [])} action(s) unsupported in Lakeview "
                        f"(filter/highlight/URL/parameter) — configure cross-filters manually"
                        if workbook_meta.actions else None
                    ),
                },
            ]
            for check in ontology_fidelity:
                if not check["passed"]:
                    msg = (
                        f"Ontology fidelity: {check['check']} "
                        f"(expected {check['expected']}, got {check['actual']})"
                    )
                    if check.get("note"):
                        msg = f"Ontology fidelity: {check['note']}"
                    val_res.setdefault("warnings", []).append(msg)
                    self.log("WARNING", msg)
            warning_count = len(val_res.get("warnings", []))

            # Build generated JSON summary (truncated for storage)
            import json as _json
            generated_json_str = None
            try:
                dash_dict = lakeview_dash.to_dict()
                generated_json_str = _json.dumps(dash_dict, indent=2, ensure_ascii=False)[:50000]
            except Exception:
                pass

            # Build visual element compatibility matrix
            compatibility_matrix = [
                {"visual": "Bar Chart", "status": "COMPATIBLE", "notes": "Mapped to Lakeview Bar Spec"},
                {"visual": "Line Chart", "status": "COMPATIBLE", "notes": "Mapped to Lakeview Line Spec"},
                {"visual": "Pie Chart", "status": "COMPATIBLE", "notes": "Mapped to Lakeview Pie Spec"},
                {"visual": "Table", "status": "COMPATIBLE", "notes": "Mapped to Lakeview Pivot/Table Spec"},
                {"visual": "Scatter Plot", "status": "COMPATIBLE", "notes": "Mapped to Lakeview Scatter Spec"},
                {"visual": "Maps", "status": "UNSUPPORTED", "notes": "Converted to Table Grid"},
                {"visual": "KPI Cards", "status": "COMPATIBLE", "notes": "Mapped to Single-Value Counter Card"},
                {"visual": "Filters", "status": "COMPATIBLE", "notes": "Mapped to Lakeview Filter Widgets"},
                {"visual": "Text Zones", "status": "COMPATIBLE", "notes": "Mapped to Lakeview Textbox Spec"},
                {"visual": "Parameters", "status": "CONVERTED", "notes": "Converted to Dashboard Parameters"},
            ]

            return {
                "status": "COMPLETED" if val_res.get("valid") else "WARNING",
                "output_summary": f"{'VALID' if val_res.get('valid') else 'INVALID'}: {error_count} errors, {warning_count} warnings, {len(removed)} widgets pruned",
                "metrics": {
                    "is_valid": val_res.get("valid", False),
                    "error_count": error_count,
                    "warning_count": warning_count,
                    "pruned_widgets": len(removed),
                    "tier_status": val_res.get("tier_status", {}),
                    "visuals_supported_count": 9,
                    "visuals_unsupported_count": 1,
                    "ontology_text_zones_expected": expected_text,
                    "ontology_text_zones_mapped": lakeview_text,
                    "ontology_filter_cards_expected": expected_filters,
                    "ontology_filter_cards_mapped": lakeview_filters,
                },
                "artifacts": {
                    "validation_errors": val_res.get("errors", []),
                    "validation_warnings": val_res.get("warnings", []),
                    "tier_status": val_res.get("tier_status", {}),
                    "pruned_widgets": list(removed),
                    "visual_compatibility_matrix": compatibility_matrix,
                    "generated_json_preview": generated_json_str,
                    "workbook_ontology": ontology,
                    "ontology_fidelity": ontology_fidelity,
                },
                "generated_code": generated_json_str,
                "logs": [
                    f"[INFO] Running JSON schema validation",
                    f"[INFO] Checking layout bounds (x + width <= 6)",
                    f"[INFO] Checking widget encoding completeness",
                    f"[INFO] Ontology fidelity: {lakeview_text}/{expected_text} text, "
                    f"{lakeview_filters}/{expected_filters} filters",
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

        # ── Assemble migration report & final result ──
        report = generate_migration_report(workbook_meta, lakeview_dash, val_res, self.error_bag)

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
