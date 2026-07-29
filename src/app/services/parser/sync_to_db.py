import logging
import time
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models.metadata import WorkbookMetadata
from app.models.db_models import (
    Workbook, Dashboard, Worksheet, CalculatedField,
    DatasourceModel, TableModel, TableJoin
)

logger = logging.getLogger(__name__)


def _retry_commit(session: Session, max_retries: int = 5, label: str = ""):
    for attempt in range(1, max_retries + 1):
        try:
            session.commit()
            return
        except OperationalError as exc:
            if "database is locked" in str(exc) and attempt < max_retries:
                wait = 0.5 * (2 ** (attempt - 1))
                logger.warning("DB locked during %s (attempt %d/%d), retrying in %.1fs...", label or "commit", attempt, max_retries, wait)
                session.rollback()
                time.sleep(wait)
            else:
                raise


def sync_metadata_to_db(metadata: WorkbookMetadata, db_session: Session, job_id: int = None) -> Workbook:
    """Persists parsed TOM metadata model into SQLite database."""
    wb_orm = Workbook(
        job_id=job_id,
        name=metadata.source_file.replace('.twbx', '').replace('.twb', ''),
        source_file=metadata.source_file,
        version=metadata.version,
    )
    db_session.add(wb_orm)
    db_session.flush()

    # Persist Datasources, Tables, Joins
    for ds in metadata.datasources:
        ds_orm = DatasourceModel(
            workbook_id=wb_orm.id,
            name=ds.name,
            caption=ds.caption
        )
        db_session.add(ds_orm)
        db_session.flush()

        for tbl in ds.tables:
            tbl_orm = TableModel(
                datasource_id=ds_orm.id,
                name=tbl.name,
                columns=tbl.columns
            )
            db_session.add(tbl_orm)

        for join in ds.joins:
            join_orm = TableJoin(
                datasource_id=ds_orm.id,
                left_table=join.left_table,
                right_table=join.right_table,
                join_type=join.join_type,
                left_column=join.left_column,
                right_column=join.right_column
            )
            db_session.add(join_orm)

    # Persist Dashboards & Worksheets
    for db in metadata.dashboards:
        db_orm = Dashboard(
            workbook_id=wb_orm.id,
            name=db.name,
            raw_metadata={"worksheets": db.worksheets}
        )
        db_session.add(db_orm)
        db_session.flush()

        for ws in metadata.worksheets:
            if ws.name in db.worksheets:
                ws_orm = Worksheet(
                    workbook_id=wb_orm.id,
                    dashboard_id=db_orm.id,
                    name=ws.name,
                    rows=ws.rows,
                    columns=ws.columns,
                    mark_type=ws.mark_type,
                    used_calculated_fields=ws.used_calculated_fields
                )
                db_session.add(ws_orm)

        for ds in metadata.datasources:
            for cf in ds.calculated_fields:
                cf_orm = CalculatedField(
                    dashboard_id=db_orm.id,
                    name=cf.name,
                    formula=cf.formula,
                    datatype=cf.datatype
                )
                db_session.add(cf_orm)

    _retry_commit(db_session, label="sync_metadata_to_db")
    return wb_orm
