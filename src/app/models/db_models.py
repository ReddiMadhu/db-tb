from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.session import Base


class MigrationJob(Base):
    """Tracks end-to-end execution of a 10-stage migration pipeline job."""
    __tablename__ = "migration_jobs"

    id = Column(Integer, primary_key=True, index=True)
    job_uuid = Column(String, unique=True, index=True)
    source_filename = Column(String)
    status = Column(String, default="INITIALIZED", index=True)  # INITIALIZED, PARSED, COMPILED, GENERATED, VALIDATED, DEPLOYED, FAILED
    current_stage = Column(Integer, default=1)
    
    output_lvdash_path = Column(String, nullable=True)
    error_bag = Column(JSON, default=list)  # Accumulates FATAL, ERROR, WARNING, INFO logs
    pipeline_config = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    workbooks = relationship("Workbook", back_populates="migration_job")
    report = relationship("MigrationReport", back_populates="migration_job", uselist=False)


class MigrationReport(Base):
    """Persists translation telemetry, validation results, and remediation steps."""
    __tablename__ = "migration_reports"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("migration_jobs.id"))
    
    total_worksheets = Column(Integer, default=0)
    successful_worksheets = Column(Integer, default=0)
    total_expressions = Column(Integer, default=0)
    rule_compiled_expressions = Column(Integer, default=0)
    llm_compiled_expressions = Column(Integer, default=0)
    unsupported_expressions = Column(Integer, default=0)
    
    layout_fidelity_score = Column(Float, default=100.0)
    report_json = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    migration_job = relationship("MigrationJob", back_populates="report")


class Workbook(Base):
    __tablename__ = "workbooks"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("migration_jobs.id"), nullable=True)
    name = Column(String, index=True)
    source_file = Column(String)
    version = Column(String, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    migration_job = relationship("MigrationJob", back_populates="workbooks")
    dashboards = relationship("Dashboard", back_populates="workbook")
    worksheets = relationship("Worksheet", back_populates="workbook")
    datasources = relationship("DatasourceModel", back_populates="workbook")


class Dashboard(Base):
    __tablename__ = "dashboards"

    id = Column(Integer, primary_key=True, index=True)
    workbook_id = Column(Integer, ForeignKey("workbooks.id"))
    name = Column(String, index=True)
    complexity_score = Column(Float, nullable=True)
    raw_metadata = Column(JSON, nullable=True)

    workbook = relationship("Workbook", back_populates="dashboards")
    worksheets = relationship("Worksheet", back_populates="dashboard")
    calculated_fields = relationship("CalculatedField", back_populates="dashboard")


class Worksheet(Base):
    __tablename__ = "worksheets"

    id = Column(Integer, primary_key=True, index=True)
    workbook_id = Column(Integer, ForeignKey("workbooks.id"))
    dashboard_id = Column(Integer, ForeignKey("dashboards.id"), nullable=True)
    name = Column(String, index=True)
    used_calculated_fields = Column(JSON, default=list)
    rows = Column(JSON, default=list)
    columns = Column(JSON, default=list)
    filters_and_marks = Column(JSON, default=list)
    mark_type = Column(String, nullable=True)
    measure_bindings = Column(JSON, default=list)

    dashboard = relationship("Dashboard", back_populates="worksheets")
    workbook = relationship("Workbook", back_populates="worksheets")


class CalculatedField(Base):
    __tablename__ = "calculated_fields"

    id = Column(Integer, primary_key=True, index=True)
    dashboard_id = Column(Integer, ForeignKey("dashboards.id"))
    name = Column(String)
    formula = Column(Text)
    translated_sql = Column(Text, nullable=True)
    datatype = Column(String)

    dashboard = relationship("Dashboard", back_populates="calculated_fields")


class DatasourceModel(Base):
    __tablename__ = "datasources"

    id = Column(Integer, primary_key=True, index=True)
    workbook_id = Column(Integer, ForeignKey("workbooks.id"))
    name = Column(String, index=True)
    caption = Column(String, nullable=True)

    workbook = relationship("Workbook", back_populates="datasources")
    tables = relationship("TableModel", back_populates="datasource")
    joins = relationship("TableJoin", back_populates="datasource")


class TableModel(Base):
    __tablename__ = "tables"

    id = Column(Integer, primary_key=True, index=True)
    datasource_id = Column(Integer, ForeignKey("datasources.id"))
    name = Column(String, index=True)
    columns = Column(JSON, nullable=True)

    datasource = relationship("DatasourceModel", back_populates="tables")


class TableJoin(Base):
    __tablename__ = "table_joins"

    id = Column(Integer, primary_key=True, index=True)
    datasource_id = Column(Integer, ForeignKey("datasources.id"))
    left_table = Column(String)
    right_table = Column(String)
    join_type = Column(String)
    left_column = Column(String)
    right_column = Column(String)

    datasource = relationship("DatasourceModel", back_populates="joins")
