import sys
import json
import sqlite3
import os

sys.path.insert(0, "src")

from app.services.pipeline import MigrationPipeline
from app.db.session import SessionLocal
from app.models.db_models import MigrationJob

db = SessionLocal()

job = db.query(MigrationJob).filter(MigrationJob.job_uuid == "33c429493082").first()
if job:
    upload_path = job.pipeline_config.get("upload_path")
    print(f"Re-executing pipeline for job {job.job_uuid} (file: {upload_path})...")
    pipeline = MigrationPipeline(upload_path)
    res = pipeline.run()
    
    output_path = job.output_lvdash_path
    res["lakeview_dashboard"].save_to_file(output_path)
    
    job.status = res["status"]
    job.current_stage = 10
    job.error_bag = json.dumps(res["error_bag"])
    db.commit()

    print("Pipeline re-execution complete!")
    print("New Job Status:", job.status)
    print("Error Bag:", job.error_bag)
db.close()
