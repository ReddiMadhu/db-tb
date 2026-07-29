# Architecture Specification

## Overview

The **Tableau → Databricks Lakeview Migration Engine** is a production-grade, modular monolith built with Python 3.11, FastAPI, SQLite (WAL mode), and SQLAlchemy. It converts Tableau workbooks (`.twb` / `.twbx`) into validated Databricks Lakeview (`serialized_dashboard`) JSON objects and Databricks Asset Bundles (`databricks.yml`).

## System Architecture

```
Tableau Workbook (.twb / .twbx)
        │
        ▼
[Stage 1-3: XML Parser & Extractor] ──► SQLite DB (migrations.db)
        │
        ▼
[Stage 4: Dependency Graph (networkx)]
        │
        ▼
[Stage 5-6: Compiler & Dialect Engine (sqlglot + LLM Retry Loop)]
        │
        ▼
[Stage 7: Universal BI Model (UBIM) & Optimizer]
        │
        ▼
[Stage 8: Lakeview Generator & Layout Grid Engine (6-col grid)]
        │
        ▼
[Stage 9: 6-Tier Validation Suite]
        │
        ▼
[Stage 10: Multi-Channel Publisher (REST / SDK / DABs)]
```

## Layered Modules

1. **Presentation Layer**: FastAPI REST API (`/api/v1/migrations/...`)
2. **Pipeline Layer**: 10-stage orchestrator with `ErrorBag` log accumulation
3. **Parsing Engine**: `tableau_extractor.py` (14 XML extraction functions) + `mark_type_resolver.py`
4. **Dependency Engine**: `dependency_graph.py` (`networkx.DiGraph` DAG)
5. **Compiler Layer**: `expression_compiler.py` (120+ functions + LOD regex rules) + `expression_agent.py` (LLM fallback with `sqlglot` Spark SQL validation retry loop)
6. **SQL Translator**: `sqlglot` dialect converter (TSQL/Postgres/Oracle -> Spark SQL)
7. **Normalizer Engine**: `tom_to_ubim.py` (TOM -> UBIM) + `optimizer.py` (query dedup & pruning)
8. **Generator Engine**: `layout_engine.py` (6-column grid matrix) + `lakeview_generator.py`
9. **Validator Engine**: 6-tier validator (`jsonschema` vs `24_json_schema.json`, `sqlglot` Spark syntax, reference integrity, 6-col bounds, widget spec versioning, cycle/ID uniqueness)
10. **Deployer Engine**: `api_client.py` (REST/SDK), `bundle_generator.py` (DABs `databricks.yml`), `diff_engine.py` (Hierarchical tree-diff)
