# Lakeview Migration Engine Architecture

This document outlines the architectural design for an enterprise migration engine, designed to programmatically migrate legacy BI dashboards (e.g., Tableau, Power BI) to Databricks Lakeview.

## 1. System Architecture Overview

The Migration Engine follows a pipeline pattern:

1. **Source Parser Layer**: Ingests and parses native BI files (Tableau `.twb` XML, Power BI `.pbit` JSON).
2. **Semantic Analyzer**: Extracts the underlying data model, relationships, and calculated fields.
3. **Intermediate Model Builder**: Normalizes the source schema into an internal universal BI model.
4. **SQL Translator**: Converts platform-specific syntax (e.g., Tableau LODs, DAX) into Databricks SQL.
5. **Layout Calculator**: Maps free-form or proprietary layouts into the strict Lakeview 6-column grid.
6. **Lakeview Generator**: Produces the final `serialized_dashboard` JSON payload.
7. **Validation Engine**: Ensures the generated JSON adheres to Lakeview schema rules.
8. **Deployment Engine**: Uses the Databricks REST API to create and publish the dashboard.
9. **Report Generator**: Outputs a migration summary, specifically flagging unsupported features.

## 2. Key Components Details

### Source Parsers
- **Tableau Parser**: Utilizes `lxml` to traverse `.twb` (XML) files. Extracts connections, worksheets, dashboards, calculated fields, and parameters.
- **Power BI Parser**: Parses unzipped `.pbit` files to extract the tabular model and visual layouts.

### Translators & Calculators
- **VizQL / DAX to SQL Translator**: A sophisticated module that maps concepts.
- **LOD to Window Function Converter**: Converts Tableau Level of Detail expressions (`FIXED`, `INCLUDE`, `EXCLUDE`) to equivalent SQL `OVER (PARTITION BY ...)` patterns.
- **Table Calculation Converter**: Translates UI-based table calcs (Running Total, % of Total) into Databricks SQL window functions.
- **Container Layout to Grid Position Calculator**: An algorithm that processes nested layout containers (horizontal/vertical) or absolute floating coordinates and projects them onto a `0 <= x <= 5` column grid without overlaps.

### Data Model Mapping
- **Unity Catalog Schema Mapper**: Identifies legacy data sources and maps them to registered tables and views within Databricks Unity Catalog.

## 3. Recommended Tech Stack
- **Core Engine**: Python 3.10+
- **XML Parsing**: `lxml`
- **API Interaction**: `databricks-sdk-py` (Databricks SDK for Python)
- **Validation**: `jsonschema`
- **Template Generation**: `Jinja2` (or direct dict serialization via `json`)
- **SQL Parsing/Formatting**: `sqlglot` (for dialect translation)

## 4. Migration Workflow

1. **Source Analysis**: Identify dashboards suitable for migration.
2. **Parse**: Extract XML/JSON definitions.
3. **Translate**: Convert data models and expressions to Databricks SQL.
4. **Generate**: Map visuals to Lakeview widget specs and layout arrays.
5. **Validate**: Run against internal JSON schemas representing Lakeview rules.
6. **Deploy**: Call `POST /api/2.0/workspace/lakeview/dashboards`.
7. **Verify**: Retrieve via GET and check status.
8. **Report**: Generate a markdown/HTML report of success rate, visual mapping degradations, and manual remediation steps.

## 5. Risk Mitigation & Edge Cases
- **Feature Parity Gaps**: Many visuals (e.g., gauges) must fallback to supported types (e.g., KPI counters or bar charts).
- **SQL Dialect Differences**: Extreme care needed for date functions and custom string manipulations.
- **Layout Precision Loss**: Converting floating objects to a 6-column grid will result in visual shifts.
- **Performance**: High-complexity dashboards with dozens of visuals may struggle on small SQL Warehouses.
- **Data Security**: Row Level Security implemented in the BI tool must be pushed down to Unity Catalog table grants or dynamic views.
