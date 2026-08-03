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

        # Persist Upload stage result for frontend pipeline visualization
        try:
            from app.models.stage_model import StageResult, PIPELINE_STAGE_DEFS
            upload_def = PIPELINE_STAGE_DEFS[0]  # Upload is stage 1
            upload_stage = StageResult(
                job_uuid=job_uuid,
                stage_id=upload_def["id"],
                stage_number=upload_def["number"],
                stage_name=upload_def["name"],
                status="COMPLETED",
                started_at=job.created_at,
                completed_at=datetime.utcnow(),
                duration_ms=0,
                input_summary=f"{file.filename} ({os.path.getsize(saved_file_path)} bytes)",
                output_summary=f"Uploaded and parsed: {len(workbook_meta.datasources)} datasources, {len(workbook_meta.worksheets)} worksheets, {len(workbook_meta.dashboards)} dashboards",
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
                logs=[
                    f"[INFO] Received {file.filename}",
                    f"[INFO] File saved to {saved_file_path}",
                    f"[INFO] Extracted {len(embedded_files)} embedded files" if embedded_files else "[INFO] No embedded files",
                    f"[SUCCESS] Upload completed successfully",
                ],
                warnings=[],
                errors=[],
            )
            db.add(upload_stage)
            db.commit()
        except Exception as e:
            logger.warning("Failed to persist upload stage result: %s", e)

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
