import os
import json
import tempfile
import shutil
import logging
from datetime import datetime
from typing import Optional, Dict
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.db_models import MigrationJob, MigrationReport
from app.services.pipeline import MigrationPipeline
from app.services.deployer.api_client import LakeviewAPIClient
from app.services.deployer.bundle_generator import generate_databricks_asset_bundle
from app.services.deployer.diff_engine import compute_dashboard_diff

logger = logging.getLogger(__name__)

router = APIRouter()

# Output directory (same as upload.py)
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)


@router.get("/")
async def list_migration_jobs(db: Session = Depends(get_db)):
    """Returns all migration jobs."""
    jobs = db.query(MigrationJob).order_by(MigrationJob.created_at.desc()).all()
    return [
        {
            "id": j.id,
            "job_uuid": j.job_uuid,
            "source_filename": j.source_filename,
            "status": j.status,
            "current_stage": j.current_stage,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        }
        for j in jobs
    ]


from pydantic import BaseModel as PydanticBaseModel
from typing import Dict


class ExecuteRequest(PydanticBaseModel):
    table_mapping: Optional[Dict[str, str]] = None
    catalog: Optional[str] = None
    schema_name: Optional[str] = None


@router.post("/{job_uuid}/execute")
async def execute_migration_pipeline(
    job_uuid: str,
    req: Optional[ExecuteRequest] = None,
    db: Session = Depends(get_db),
):
    """Executes full 10-stage migration pipeline for a given upload job."""
    job = db.query(MigrationJob).filter(MigrationJob.job_uuid == job_uuid).first()
    if not job:
        raise HTTPException(status_code=404, detail="Migration job not found.")

    if job.status not in ("PARSED", "NEEDS_MAPPING", "FAILED"):
        raise HTTPException(
            status_code=400,
            detail=f"Job is in state '{job.status}', expected 'PARSED', 'NEEDS_MAPPING', or 'FAILED'."
        )

    upload_path = (job.pipeline_config or {}).get("upload_path")
    if not upload_path or not os.path.exists(upload_path):
        raise HTTPException(
            status_code=404,
            detail="Source workbook file not found. Please re-upload."
        )

    from app.core.config import settings
    from app.models.db_models import DatasourceMapping

    # Load saved confirmed mappings from DB
    db_mappings = (
        db.query(DatasourceMapping)
        .filter(DatasourceMapping.job_id == job.id, DatasourceMapping.status == "CONFIRMED")
        .all()
    )
    saved_table_mapping = {m.tableau_table_name: m.target_full_name for m in db_mappings if m.target_full_name}

    # Explicit request mapping overrides saved mapping
    table_mapping = {**saved_table_mapping, **((req.table_mapping if req else None) or {})}
    catalog = (req.catalog if req else None) or settings.DEFAULT_CATALOG
    schema_name = (req.schema_name if req else None) or settings.DEFAULT_SCHEMA

    try:
        job.status = "EXECUTING"
        job.current_stage = 5
        db.commit()

        pipeline = MigrationPipeline(
            upload_path,
            job_uuid=job_uuid,
            table_mapping=table_mapping,
            default_catalog=catalog,
            default_schema=schema_name,
            databricks_host=settings.DATABRICKS_HOST or "",
            databricks_token=settings.DATABRICKS_TOKEN or "",
            warehouse_id=settings.DEFAULT_WAREHOUSE_ID or "",
        )
        result = pipeline.run()

        workbook_meta = result["workbook_meta"]
        lakeview_dash = result["lakeview_dashboard"]
        val_res = result["validation_results"]
        report = result["report"]
        error_bag = result["error_bag"]

        # Fail-closed: never persist blank chart shells (pipeline already pruned;
        # re-check as a hard gate before write).
        from app.services.validator.validation_engine import (
            prune_incomplete_widgets,
            _widget_is_incomplete_chart,
        )
        extra_removed = prune_incomplete_widgets(lakeview_dash)
        if extra_removed:
            for title in extra_removed:
                error_bag.append({
                    "level": "ERROR",
                    "message": f"Blocked incomplete widget '{title}' from save.",
                })
            val_res["valid"] = False
            result["status"] = "FAILED_VALIDATION"

        still_incomplete = any(
            _widget_is_incomplete_chart(item.widget)
            for page in lakeview_dash.pages
            for item in page.layout
        )
        if still_incomplete:
            raise HTTPException(
                status_code=500,
                detail="Refusing to save dashboard containing incomplete chart widgets "
                       "(empty encodings or queries).",
            )

        # Save generated Lakeview JSON to disk (pruned; no blank shells)
        job_output_dir = os.path.join(OUTPUT_DIR, job_uuid)
        os.makedirs(job_output_dir, exist_ok=True)
        output_filename = f"{job_uuid}.lvdash.json"
        output_path = os.path.join(job_output_dir, output_filename)
        lakeview_dash.save_to_file(output_path)

        # Also save a pretty-printed version for inspection
        pretty_path = os.path.join(job_output_dir, f"{job_uuid}_pretty.lvdash.json")
        with open(pretty_path, "w", encoding="utf-8") as f:
            json.dump(lakeview_dash.to_dict(), f, indent=2, ensure_ascii=False)

        # Update job record
        job.status = result["status"]
        job.current_stage = 10
        job.output_lvdash_path = output_path
        job.error_bag = error_bag
        job.completed_at = datetime.utcnow()
        db.commit()

        # Persist MigrationReport
        existing_report = db.query(MigrationReport).filter(MigrationReport.job_id == job.id).first()
        if existing_report:
            db.delete(existing_report)
            db.commit()

        summary = report.get("summary", {})
        report_orm = MigrationReport(
            job_id=job.id,
            total_worksheets=summary.get("worksheets_total", 0),
            successful_worksheets=summary.get("worksheets_total", 0),
            total_expressions=summary.get("expressions_total", 0),
            rule_compiled_expressions=summary.get("expressions_rule_compiled", 0),
            llm_compiled_expressions=summary.get("expressions_lod_compiled", 0),
            unsupported_expressions=summary.get("expressions_unsupported", 0),
            report_json=report,
        )
        db.add(report_orm)
        db.commit()

        response = {
            "job_uuid": job_uuid,
            "status": result["status"],
            "current_stage": 10,
            "output_file": output_path,
            "summary": report.get("summary", {}),
            "target_lakeview": report.get("target_lakeview", {}),
            "validation_valid": val_res["valid"],
            "validation_errors": val_res.get("errors", []),
            "validation_warnings": val_res.get("warnings", []),
            "error_bag_count": len(error_bag),
            "message": "10-Stage migration pipeline completed successfully."
                if val_res["valid"]
                else "Pipeline completed with validation errors."
        }

        # Include Databricks sources info for Data Model screen
        if "databricks_sources" in result:
            response["databricks_sources"] = result["databricks_sources"]
        if "semantic_model_summary" in result:
            response["semantic_model_summary"] = result["semantic_model_summary"]

        return response
    except Exception as e:
        logger.exception("Pipeline execution failed for job %s", job_uuid)
        job.status = "FAILED"
        job.error_bag = (job.error_bag or []) + [
            {"level": "FATAL", "message": f"Pipeline execution failed: {str(e)}"}
        ]
        db.commit()
        raise HTTPException(status_code=500, detail=f"Pipeline execution failed: {str(e)}")


@router.get("/{job_uuid}/status")
async def get_migration_status(job_uuid: str, db: Session = Depends(get_db)):
    """Retrieves current status, stage progress, and error bag for a job."""
    job = db.query(MigrationJob).filter(MigrationJob.job_uuid == job_uuid).first()
    if not job:
        raise HTTPException(status_code=404, detail="Migration job not found.")

    return {
        "job_uuid": job.job_uuid,
        "filename": job.source_filename,
        "status": job.status,
        "current_stage": job.current_stage,
        "error_bag": job.error_bag,
        "has_output": bool(job.output_lvdash_path and os.path.exists(job.output_lvdash_path)),
        "created_at": str(job.created_at),
        "completed_at": str(job.completed_at) if job.completed_at else None
    }


@router.get("/{job_uuid}/json")
async def download_lakeview_json(job_uuid: str, db: Session = Depends(get_db)):
    """Downloads the generated Lakeview .lvdash.json file."""
    job = db.query(MigrationJob).filter(MigrationJob.job_uuid == job_uuid).first()
    if not job:
        raise HTTPException(status_code=404, detail="Migration job not found.")

    if not job.output_lvdash_path or not os.path.exists(job.output_lvdash_path):
        raise HTTPException(
            status_code=404,
            detail="Generated dashboard JSON not found. Run /execute first."
        )

    return FileResponse(
        job.output_lvdash_path,
        media_type="application/json",
        filename=f"{job_uuid}.lvdash.json"
    )


@router.get("/{job_uuid}/report")
async def get_migration_report(job_uuid: str, db: Session = Depends(get_db)):
    """Returns the migration telemetry report for a completed job."""
    job = db.query(MigrationJob).filter(MigrationJob.job_uuid == job_uuid).first()
    if not job:
        raise HTTPException(status_code=404, detail="Migration job not found.")

    report = db.query(MigrationReport).filter(MigrationReport.job_id == job.id).first()
    if not report:
        raise HTTPException(
            status_code=404,
            detail="Migration report not found. Run /execute first."
        )

    return {
        "job_uuid": job_uuid,
        "filename": job.source_filename,
        "total_worksheets": report.total_worksheets,
        "successful_worksheets": report.successful_worksheets,
        "total_expressions": report.total_expressions,
        "rule_compiled_expressions": report.rule_compiled_expressions,
        "llm_compiled_expressions": report.llm_compiled_expressions,
        "unsupported_expressions": report.unsupported_expressions,
        "layout_fidelity_score": report.layout_fidelity_score,
        "detailed_report": report.report_json,
    }


class DeployRequest(PydanticBaseModel):
    warehouse_id: str
    host: Optional[str] = None
    token: Optional[str] = None
    catalog: Optional[str] = None
    schema_name: Optional[str] = None


@router.post("/{job_uuid}/deploy")
async def deploy_to_databricks(
    job_uuid: str,
    req: DeployRequest,
    db: Session = Depends(get_db)
):
    """Deploys generated Lakeview dashboard directly to Databricks workspace via REST/SDK API."""
    job = db.query(MigrationJob).filter(MigrationJob.job_uuid == job_uuid).first()
    if not job:
        raise HTTPException(status_code=404, detail="Migration job not found.")

    if not job.output_lvdash_path or not os.path.exists(job.output_lvdash_path):
        raise HTTPException(
            status_code=404,
            detail="Generated dashboard JSON not found. Run /execute first."
        )

    try:
        client = LakeviewAPIClient(host=req.host, token=req.token)
        with open(job.output_lvdash_path, "r", encoding="utf-8") as f:
            serialized_json = f.read()

        result = client.create_dashboard(
            display_name=job.source_filename.replace('.twbx', '').replace('.twb', ''),
            serialized_dashboard=serialized_json,
            warehouse_id=req.warehouse_id,
            dataset_catalog=req.catalog or None,
            dataset_schema=req.schema_name or None,
        )

        job.status = "DEPLOYED"
        db.commit()

        return {
            "status": "SUCCESS",
            "dashboard_id": result.get("dashboard_id"),
            "published_url": f"{client.host}/dashboardsv3/{result.get('dashboard_id')}/published"
                if client.host else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Databricks deployment failed: {str(e)}")


@router.get("/{job_uuid}/bundle")
async def generate_asset_bundle(job_uuid: str, db: Session = Depends(get_db)):
    """Generates a Databricks Asset Bundle (DABs) databricks.yml configuration file."""
    job = db.query(MigrationJob).filter(MigrationJob.job_uuid == job_uuid).first()
    if not job:
        raise HTTPException(status_code=404, detail="Migration job not found.")

    if not job.output_lvdash_path or not os.path.exists(job.output_lvdash_path):
        raise HTTPException(
            status_code=404,
            detail="Generated dashboard JSON not found. Run /execute first."
        )

    # Generate bundle using the actual Lakeview dashboard output
    from app.models.lakeview_model import LakeviewDashboard
    with open(job.output_lvdash_path, "r", encoding="utf-8") as f:
        dash_dict = json.load(f)

    # Re-construct LakeviewDashboard from saved JSON
    from app.models.lakeview_model import Dataset, Page, Widget, Position
    datasets = [Dataset(**d) for d in dash_dict.get("datasets", [])]
    pages = []
    for p in dash_dict.get("pages", []):
        widgets = []
        for w in p.get("widgets", []):
            pos_data = w.get("position", {})
            widget = Widget(
                name=w.get("name", ""),
                datasetName=w.get("datasetName"),
                spec=w.get("spec"),
                position=Position(**pos_data)
            )
            widgets.append(widget)
        pages.append(Page(name=p.get("name", ""), displayName=p.get("displayName", ""), widgets=widgets))

    lakeview_dash = LakeviewDashboard(datasets=datasets, pages=pages)

    bundle_dir = os.path.join(OUTPUT_DIR, job_uuid, "bundle")
    os.makedirs(bundle_dir, exist_ok=True)
    dashboard_name = job.source_filename.replace('.twbx', '').replace('.twb', '')

    res = generate_databricks_asset_bundle(dashboard_name, lakeview_dash, bundle_dir)
    with open(res["yaml_path"], "r", encoding="utf-8") as f:
        yaml_content = f.read()

    return {
        "status": "SUCCESS",
        "databricks_yml": yaml_content,
        "bundle_path": bundle_dir
    }


@router.get("/{job_uuid}/diff")
async def compute_diff(
    job_uuid: str,
    existing_dashboard_path: str = None,
    db: Session = Depends(get_db)
):
    """Computes diff between generated dashboard and an existing Databricks Lakeview dashboard."""
    job = db.query(MigrationJob).filter(MigrationJob.job_uuid == job_uuid).first()
    if not job:
        raise HTTPException(status_code=404, detail="Migration job not found.")

    if not job.output_lvdash_path or not os.path.exists(job.output_lvdash_path):
        raise HTTPException(
            status_code=404,
            detail="Generated dashboard JSON not found. Run /execute first."
        )

    # Load the generated dashboard
    from app.models.lakeview_model import LakeviewDashboard, Dataset, Page, Widget, Position
    with open(job.output_lvdash_path, "r", encoding="utf-8") as f:
        new_dash_dict = json.load(f)

    # Load existing dashboard (from file or empty baseline)
    existing_dict = {"datasets": [], "pages": []}
    if existing_dashboard_path and os.path.exists(existing_dashboard_path):
        with open(existing_dashboard_path, "r", encoding="utf-8") as f:
            existing_dict = json.load(f)

    # Re-construct LakeviewDashboard for diff engine
    datasets = [Dataset(**d) for d in new_dash_dict.get("datasets", [])]
    pages = []
    for p in new_dash_dict.get("pages", []):
        widgets = [
            Widget(
                name=w.get("name", ""),
                datasetName=w.get("datasetName"),
                spec=w.get("spec"),
                position=Position(**w.get("position", {}))
            ) for w in p.get("widgets", [])
        ]
        pages.append(Page(name=p.get("name", ""), displayName=p.get("displayName", ""), widgets=widgets))

    new_lakeview = LakeviewDashboard(datasets=datasets, pages=pages)
    diff = compute_dashboard_diff(existing_dict, new_lakeview)

    return {
        "job_uuid": job_uuid,
        "diff": diff
    }
