import os
from typing import Dict, Any
from app.models.metadata import WorkbookMetadata
from app.services.parser.tableau_extractor import parse_workbook
from app.services.parser.dependency_graph import DependencyGraphEngine
from app.services.normalizer.tom_to_ubim import normalize_tom_to_ubim
from app.services.normalizer.optimizer import optimize_ubim
from app.services.generator.lakeview_generator import generate_lakeview_dashboard
from app.services.validator.validation_engine import validate_lakeview_dashboard
from app.services.reporter.migration_report import generate_migration_report
from app.services.mapper.datasource_mapper import build_table_mapping


class MigrationPipeline:
    """10-Stage Migration Pipeline Orchestrator with ErrorBag log accumulation."""

    def __init__(
        self,
        file_path: str,
        table_mapping: Dict[str, str] = None,
        default_catalog: str = "",
        default_schema: str = "",
    ):
        self.file_path = file_path
        self.table_mapping = table_mapping or {}
        self.default_catalog = default_catalog
        self.default_schema = default_schema
        self.error_bag = []

    def log(self, level: str, message: str):
        self.error_bag.append({"level": level, "message": message})

    def run(self) -> Dict[str, Any]:
        # Stage 1 & 2 & 3: Extract Tableau XML into TOM
        self.log("INFO", f"Stage 1-3: Parsing {os.path.basename(self.file_path)}")
        workbook_meta: WorkbookMetadata = parse_workbook(self.file_path)

        # Stage 4: Dependency Graph
        self.log("INFO", "Stage 4: Building dependency graph DAG")
        dag_engine = DependencyGraphEngine(workbook_meta)
        cycles = dag_engine.detect_cycles()
        if cycles:
            self.log("ERROR", f"Circular references detected in formulas: {cycles}")

        # Stage 5: Datasource Mapping — resolve table names before SQL generation
        self.log("INFO", "Stage 5: Resolving datasource table mappings")
        _, unresolved_tables = build_table_mapping(
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

        # Stage 6: Expression & SQL Translation — build canonical field resolver
        self.log("INFO", "Stage 6: Compiling expressions & building canonical field resolver")
        from app.services.compiler.canonical_field_resolver import CanonicalFieldResolver
        field_resolver = CanonicalFieldResolver(workbook_meta)

        # Log resolver diagnostics
        excluded = [f for f in field_resolver.dump_registry() if f['is_excluded']]
        if excluded:
            for exc in excluded:
                self.log("INFO", f"Excluding field '{exc['internal_name']}' ({exc['exclude_reason']})")

        # Stage 7: Universal BI Model Normalization & Optimization
        self.log("INFO", "Stage 7: Normalizing TOM to Universal BI Model (UBIM)")
        ubim = normalize_tom_to_ubim(
            workbook_meta,
            table_mapping=self.table_mapping,
            default_catalog=self.default_catalog,
            default_schema=self.default_schema,
            field_resolver=field_resolver,
        )
        ubim_opt = optimize_ubim(ubim)

        # Stage 8: Lakeview Generator & Layout Grid Engine
        self.log("INFO", "Stage 8: Generating Lakeview JSON & projecting 6-column layout grid")
        lakeview_dash = generate_lakeview_dashboard(ubim_opt)

        # Stage 9: 6-Tier Validation Engine
        self.log("INFO", "Stage 9: Executing 6-tier validation suite")
        val_res = validate_lakeview_dashboard(lakeview_dash)
        for err in val_res.get("errors", []):
            self.log("ERROR", err)
        for warn in val_res.get("warnings", []):
            self.log("WARNING", warn)

        # Stage 10: Reporting & Telemetry
        self.log("INFO", "Stage 10: Assembling migration report")
        report = generate_migration_report(workbook_meta, lakeview_dash, val_res, self.error_bag)

        return {
            "status": "COMPLETED" if val_res["valid"] else "FAILED_VALIDATION",
            "workbook_meta": workbook_meta,
            "lakeview_dashboard": lakeview_dash,
            "validation_results": val_res,
            "report": report,
            "error_bag": self.error_bag
        }
