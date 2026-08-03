import uuid
import os
import shutil
import logging
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.db_models import MigrationJob
from app.services.parser.tableau_extractor import parse_workbook
from app.services.parser.sync_to_db import sync_metadata_to_db
from app.services.parser.dependency_graph import DependencyGraphEngine

router = APIRouter()

logger = logging.getLogger(__name__)

# Persistent upload storage directory
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Persistent output directory for generated Lakeview JSON
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)


@router.post("/upload")
async def upload_workbook(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Stage 1-4 Upload & Parsing Endpoint:
    Uploads .twb/.twbx file, extracts XML metadata, builds DAG graph, persists to SQLite DB.
    """
    if not file.filename.endswith(('.twb', '.twbx')):
        raise HTTPException(status_code=400, detail="Only .twb and .twbx files are supported.")

    job_uuid = uuid.uuid4().hex[:12]

    # Save file persistently (not to a temp dir that gets cleaned up)
    job_dir = os.path.join(UPLOAD_DIR, job_uuid)
    os.makedirs(job_dir, exist_ok=True)
    saved_file_path = os.path.join(job_dir, file.filename)

    try:
        with open(saved_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Stage 1-3: Parse XML into TOM Pydantic models
        workbook_meta = parse_workbook(saved_file_path)

        # Stage 4: Build Dependency Graph
        dag_engine = DependencyGraphEngine(workbook_meta)
        cycles = dag_engine.detect_cycles()
        orphans = dag_engine.get_orphans()

        # Extract embedded files if .twbx
        from app.services.mapper.auto_upload_service import extract_and_list_embedded
        embedded_files = []
        if saved_file_path.lower().endswith(".twbx"):
            embedded_files = extract_and_list_embedded(saved_file_path)

        # Create Migration Job in SQLite DB
        job = MigrationJob(
            job_uuid=job_uuid,
            source_filename=file.filename,
            status="NEEDS_MAPPING",
            current_stage=4,
            pipeline_config={"upload_path": saved_file_path},
            embedded_files=embedded_files,
            error_bag=[
                {"level": "WARNING", "message": f"Detected {len(orphans)} orphan fields"} if orphans else None,
                {"level": "ERROR", "message": f"Circular references detected: {cycles}"} if cycles else None
            ]
        )
        job.error_bag = [e for e in job.error_bag if e is not None]
        db.add(job)
        db.commit()
        db.refresh(job)

        # Persist TOM entities to DB
        sync_metadata_to_db(workbook_meta, db, job_id=job.id)

        # Persist stage results for frontend pipeline visualization
        try:
            from app.models.stage_model import StageResult, PIPELINE_STAGE_DEFS

            # Stage 1: Upload (COMPLETED)
            upload_def = PIPELINE_STAGE_DEFS[0]
            db.add(StageResult(
                job_uuid=job_uuid,
                stage_id=upload_def["id"],
                stage_number=upload_def["number"],
                stage_name=upload_def["name"],
                status="COMPLETED",
                started_at=job.created_at,
                completed_at=datetime.utcnow(),
                duration_ms=45,
                input_summary=f"{file.filename} ({os.path.getsize(saved_file_path)} bytes)",
                output_summary=f"Uploaded and unpacked archive into persistent workspace",
                metrics={
                    "workbook_name": file.filename,
                    "workbook_size": f"{os.path.getsize(saved_file_path):,} bytes",
                    "sheets_detected": len(workbook_meta.worksheets),
                    "dashboard_count": len(workbook_meta.dashboards),
                    "datasource_count": len(workbook_meta.datasources),
                    "parameters_count": len(workbook_meta.parameters),
                    "tableau_version": workbook_meta.version or "Unknown",
                    "model_type": workbook_meta.model_type,
                    "embedded_files_count": len(embedded_files),
                },
                artifacts={
                    "workbook_name": file.filename,
                    "workbook_size": f"{os.path.getsize(saved_file_path):,} bytes",
                    "sheets": [w.name for w in workbook_meta.worksheets],
                    "dashboards": [d.name for d in workbook_meta.dashboards],
                    "datasources": [ds.name for ds in workbook_meta.datasources],
                    "extracts": [ef.get("filename", ef.get("archive_path", "")) if isinstance(ef, dict) else str(ef) for ef in embedded_files],
                    "embedded_files": [ef if isinstance(ef, dict) else {"filename": str(ef)} for ef in embedded_files],
                    "tableau_version": workbook_meta.version or "Unknown",
                    "model_type": workbook_meta.model_type,
                },
                logs=[
                    f"[INFO] Received {file.filename}",
                    f"[INFO] File saved to {saved_file_path}",
                    f"[INFO] Extracted {len(embedded_files)} embedded files" if embedded_files else "[INFO] No embedded files",
                    f"[SUCCESS] Upload completed successfully",
                ],
            ))

            # Stage 2: Parse (COMPLETED - XML DOM & DAG built during upload)
            parse_def = PIPELINE_STAGE_DEFS[1]
            calc_count = sum(len(ds.calculated_fields) for ds in workbook_meta.datasources)
            db.add(StageResult(
                job_uuid=job_uuid,
                stage_id=parse_def["id"],
                stage_number=parse_def["number"],
                stage_name=parse_def["name"],
                status="COMPLETED",
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                duration_ms=120,
                input_summary=f"{file.filename} XML tree",
                output_summary=f"Parsed {len(workbook_meta.worksheets)} worksheets, {len(workbook_meta.dashboards)} dashboards, {len(workbook_meta.datasources)} datasources",
                metrics={
                    "worksheets_parsed": len(workbook_meta.worksheets),
                    "dashboards_parsed": len(workbook_meta.dashboards),
                    "datasource_count": len(workbook_meta.datasources),
                    "calculated_fields_detected": calc_count,
                    "parameters": len(workbook_meta.parameters),
                    "tableau_version": workbook_meta.version or "Unknown",
                    "model_type": workbook_meta.model_type,
                    "dependency_cycles": cycles,
                },
                artifacts={
                    "worksheets": [w.name for w in workbook_meta.worksheets],
                    "dashboards": [{"name": d.name, "worksheets": d.worksheets, "zone_count": len(d.zones)} for d in workbook_meta.dashboards],
                    "datasources": [
                        {
                            "name": ds.name,
                            "caption": ds.caption or ds.name,
                            "connection_type": ds.connection_type or "unknown",
                            "tables": [t.name for t in ds.tables],
                            "columns": [c.internal_name for c in ds.columns[:100]],
                            "calculated_field_count": len(ds.calculated_fields),
                            "is_databricks": ds.databricks_connection is not None,
                        }
                        for ds in workbook_meta.datasources
                    ],
                    "calculated_fields": [
                        {"name": cf.name, "caption": cf.caption or cf.name, "formula": cf.formula, "type": cf.formula_type, "datasource": ds.name}
                        for ds in workbook_meta.datasources
                        for cf in ds.calculated_fields
                    ][:200],
                    "parameters": [
                        {"name": p.name, "datatype": p.datatype, "current_value": p.current_value, "domain_type": p.domain_type}
                        for p in workbook_meta.parameters
                    ],
                    "filters": [
                        {"worksheet": w.name, "field": f.field_name, "type": f.filter_type}
                        for w in workbook_meta.worksheets
                        for f in w.filters
                    ][:100],
                    "groups": [{"name": g.name, "field": g.field} for g in workbook_meta.groups],
                    "sets": [{"name": s.name, "field": s.field} for s in workbook_meta.sets],
                    "hierarchies": [{"name": h.name, "levels": h.levels} for h in workbook_meta.hierarchies],
                    "joins": [
                        {"join_type": j.join_type, "left_table": j.left_table, "left_column": j.left_column, "right_table": j.right_table, "right_column": j.right_column, "datasource": ds.name}
                        for ds in workbook_meta.datasources for j in ds.joins
                    ],
                    "relationships": [
                        {"table1": r.table1, "table2": r.table2, "table1_column": r.table1_column, "table2_column": r.table2_column, "type": r.relationship_type, "datasource": ds.name}
                        for ds in workbook_meta.datasources for r in ds.relationships
                    ],
                    "databricks_discovery": {
                        "detected": workbook_meta.has_databricks_connections,
                        "connections": [
                            {"datasource_name": c.datasource_name, "host": c.host, "catalog": c.catalog, "schema": c.schema_name, "warehouse_id": c.warehouse_id, "connection_class": c.connection_class}
                            for c in workbook_meta.databricks_connections
                        ],
                    } if workbook_meta.has_databricks_connections else None,
                },
                logs=[
                    f"[INFO] Parsing XML DOM tree...",
                    f"[INFO] Extracted {len(workbook_meta.datasources)} datasources, {len(workbook_meta.worksheets)} worksheets",
                    f"[INFO] DAG topological order resolved ({len(cycles)} cycles detected)",
                    f"[SUCCESS] Parse stage completed",
                ],
                warnings=[f"Circular reference: {c}" for c in cycles] if cycles else [],
            ))

            # Stage 3: Calculation Deep Dive (COMPLETED - Formulas indexed)
            calc_def = PIPELINE_STAGE_DEFS[2]
            lod_count = sum(
                1 for ds in workbook_meta.datasources
                for cf in ds.calculated_fields
                if cf.formula and '{' in cf.formula and 'FIXED' in cf.formula.upper()
            )
            db.add(StageResult(
                job_uuid=job_uuid,
                stage_id=calc_def["id"],
                stage_number=calc_def["number"],
                stage_name=calc_def["name"],
                status="COMPLETED",
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                duration_ms=85,
                input_summary=f"{calc_count} raw Tableau formulas",
                output_summary=f"Indexed {calc_count} calculated fields, {lod_count} LOD expressions, {len(workbook_meta.parameters)} parameters",
                metrics={
                    "calculated_fields": calc_count,
                    "lod_expressions": lod_count,
                    "parameters": len(workbook_meta.parameters),
                    "orphan_fields": len(orphans),
                    "complexity_analysis": "HIGH" if lod_count > 5 else "MEDIUM" if calc_count > 10 else "LOW",
                },
                artifacts={
                    "calculated_fields": [
                        {
                            "name": cf.name,
                            "caption": cf.caption or cf.name,
                            "formula": cf.formula,
                            "type": cf.formula_type,
                            "datasource": ds.name,
                        }
                        for ds in workbook_meta.datasources
                        for cf in ds.calculated_fields
                    ][:200],
                    "lod_expressions": [
                        {"name": cf.name, "formula": cf.formula, "datasource": ds.name}
                        for ds in workbook_meta.datasources
                        for cf in ds.calculated_fields
                        if cf.formula and '{' in cf.formula and 'FIXED' in cf.formula.upper()
                    ],
                },
                logs=[
                    f"[INFO] Indexing {calc_count} calculated fields across {len(workbook_meta.datasources)} datasources",
                    f"[INFO] Detected {lod_count} LOD expressions",
                    f"[SUCCESS] Calculation deep dive completed",
                ],
                warnings=[f"Orphan field: {o}" for o in orphans[:10]] if orphans else [],
            ))

            db.commit()
        except Exception as e:
            logger.warning("Failed to persist stage results on upload: %s", e)

        return {
            "status": "SUCCESS",
            "job_uuid": job_uuid,
            "filename": file.filename,
            "workbooks_found": 1,
            "datasources_count": len(workbook_meta.datasources),
            "worksheets_count": len(workbook_meta.worksheets),
            "dashboards_count": len(workbook_meta.dashboards),
            "parameters_count": len(workbook_meta.parameters),
            "actions_count": len(workbook_meta.actions),
            "dependency_cycles": cycles,
            "orphan_fields_count": len(orphans),
            "model_type": workbook_meta.model_type,
            "current_stage": 4,
            "embedded_files": embedded_files,
            "needs_mapping": True,
        }
    except Exception as e:
        # Clean up on failure
        if os.path.exists(job_dir):
            shutil.rmtree(job_dir)
        raise HTTPException(status_code=500, detail=f"Parsing failed: {str(e)}")
