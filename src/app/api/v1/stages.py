"""
Tableau to Databricks Migration — Stage Results API

Endpoints for per-stage pipeline data, enabling real-time progress
polling and detailed stage inspection from the frontend.
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.db_models import MigrationJob
from app.models.stage_model import StageResult, PIPELINE_STAGE_DEFS, PIPELINE_STAGE_COUNT

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{job_uuid}/stages")
async def get_all_stages(job_uuid: str, db: Session = Depends(get_db)):
    """Returns all pipeline stage statuses for a migration job.

    Used by the PipelineStepper component to render the horizontal
    pipeline with correct status icons and colors.
    """
    job = db.query(MigrationJob).filter(MigrationJob.job_uuid == job_uuid).first()
    if not job:
        raise HTTPException(status_code=404, detail="Migration job not found.")

    stages = (
        db.query(StageResult)
        .filter(StageResult.job_uuid == job_uuid)
        .order_by(StageResult.stage_number)
        .all()
    )

    # If no stage results exist yet, return default WAITING stages
    if not stages:
        stage_list = [
            {
                "stage_id": s["id"],
                "stage_number": s["number"],
                "stage_name": s["name"],
                "status": "COMPLETED" if s["number"] == 1 and job.status != "INITIALIZED" else "WAITING",
                "duration_ms": None,
                "metrics": {},
            }
            for s in PIPELINE_STAGE_DEFS
        ]
    else:
        stage_list = [
            {
                "stage_id": s.stage_id,
                "stage_number": s.stage_number,
                "stage_name": s.stage_name,
                "status": s.status,
                "duration_ms": s.duration_ms,
                "metrics": s.metrics or {},
            }
            for s in stages
        ]

    # Calculate overall progress
    completed_count = sum(1 for s in stage_list if s["status"] in ("COMPLETED", "WARNING"))
    running_stage = next((s for s in stage_list if s["status"] == "RUNNING"), None)
    overall_progress = int((completed_count / PIPELINE_STAGE_COUNT) * 100)

    # Determine current activity description
    current_activity = None
    current_stage_name = None
    if running_stage:
        current_stage_name = running_stage["stage_name"]
        current_activity = f"Executing: {running_stage['stage_name']}..."
    elif job.status in ("COMPLETED", "DEPLOYED"):
        current_activity = "Pipeline completed"
        current_stage_name = "Publish"
        overall_progress = 100
    elif job.status == "FAILED":
        failed_stage = next((s for s in stage_list if s["status"] == "FAILED"), None)
        current_stage_name = failed_stage["stage_name"] if failed_stage else "Unknown"
        current_activity = f"Failed at: {current_stage_name}"

    return {
        "job_uuid": job_uuid,
        "stages": stage_list,
        "overall_progress": overall_progress,
        "current_stage": current_stage_name,
        "current_activity": current_activity,
        "stage_count": PIPELINE_STAGE_COUNT,
    }


@router.get("/{job_uuid}/stages/{stage_id}")
async def get_stage_detail(job_uuid: str, stage_id: str, db: Session = Depends(get_db)):
    """Returns detailed data for a specific pipeline stage.

    Includes metrics, logs, warnings, errors, and generated code.
    Used by the StageDetailPanel component.
    """
    job = db.query(MigrationJob).filter(MigrationJob.job_uuid == job_uuid).first()
    if not job:
        raise HTTPException(status_code=404, detail="Migration job not found.")

    stage = (
        db.query(StageResult)
        .filter(StageResult.job_uuid == job_uuid, StageResult.stage_id == stage_id)
        .first()
    )

    if not stage:
        # Return a default WAITING response for stages that haven't executed
        stage_def = next((s for s in PIPELINE_STAGE_DEFS if s["id"] == stage_id), None)
        if not stage_def:
            raise HTTPException(status_code=404, detail=f"Unknown stage ID: {stage_id}")

        return {
            "stage_id": stage_id,
            "stage_number": stage_def["number"],
            "stage_name": stage_def["name"],
            "status": "WAITING",
            "started_at": None,
            "completed_at": None,
            "duration_ms": None,
            "input_summary": None,
            "output_summary": None,
            "metrics": {},
            "logs": [],
            "warnings": [],
            "errors": [],
            "generated_code": None,
            "artifacts": {},
        }

    return {
        "stage_id": stage.stage_id,
        "stage_number": stage.stage_number,
        "stage_name": stage.stage_name,
        "status": stage.status,
        "started_at": stage.started_at.isoformat() if stage.started_at else None,
        "completed_at": stage.completed_at.isoformat() if stage.completed_at else None,
        "duration_ms": stage.duration_ms,
        "input_summary": stage.input_summary,
        "output_summary": stage.output_summary,
        "metrics": stage.metrics or {},
        "logs": stage.logs or [],
        "warnings": stage.warnings or [],
        "errors": stage.errors or [],
        "generated_code": stage.generated_code,
        "artifacts": stage.artifacts or {},
    }


@router.get("/{job_uuid}/progress")
async def get_progress(job_uuid: str, db: Session = Depends(get_db)):
    """Returns real-time execution progress for frontend polling.

    Polled every 2-3 seconds during pipeline execution to update
    the progress bar and pipeline stepper.
    """
    job = db.query(MigrationJob).filter(MigrationJob.job_uuid == job_uuid).first()
    if not job:
        raise HTTPException(status_code=404, detail="Migration job not found.")

    stages = (
        db.query(StageResult)
        .filter(StageResult.job_uuid == job_uuid)
        .order_by(StageResult.stage_number)
        .all()
    )

    completed_stages = [s for s in stages if s.status in ("COMPLETED", "WARNING")]
    running_stage = next((s for s in stages if s.status == "RUNNING"), None)
    failed_stage = next((s for s in stages if s.status == "FAILED"), None)

    # Calculate elapsed time
    elapsed_ms = 0
    for s in stages:
        if s.duration_ms:
            elapsed_ms += s.duration_ms

    # Overall progress percentage
    progress_percent = int((len(completed_stages) / PIPELINE_STAGE_COUNT) * 100)
    if job.status in ("COMPLETED", "DEPLOYED"):
        progress_percent = 100

    # Current activity
    current_activity = "Waiting..."
    current_stage_id = None
    current_stage_number = None
    if running_stage:
        current_activity = f"Executing: {running_stage.stage_name}..."
        current_stage_id = running_stage.stage_id
        current_stage_number = running_stage.stage_number
    elif failed_stage:
        current_activity = f"Failed at: {failed_stage.stage_name}"
        current_stage_id = failed_stage.stage_id
        current_stage_number = failed_stage.stage_number
    elif job.status in ("COMPLETED", "DEPLOYED"):
        current_activity = "Migration completed successfully"
        current_stage_id = "PUBLISH"
        current_stage_number = PIPELINE_STAGE_COUNT

    # Compact stage statuses for the stepper
    stage_statuses = [
        {"stage_id": s.stage_id, "status": s.status, "duration_ms": s.duration_ms}
        for s in stages
    ]

    return {
        "job_uuid": job_uuid,
        "job_status": job.status,
        "overall_progress": progress_percent,
        "current_stage_id": current_stage_id,
        "current_stage_number": current_stage_number,
        "current_activity": current_activity,
        "elapsed_ms": elapsed_ms,
        "completed_stages": len(completed_stages),
        "total_stages": PIPELINE_STAGE_COUNT,
        "stage_statuses": stage_statuses,
        "is_running": job.status == "EXECUTING",
        "is_complete": job.status in ("COMPLETED", "DEPLOYED"),
        "is_failed": job.status == "FAILED",
    }
