# Lakeview Dashboard Validation Rules

This document outlines the strict validation rules enforced by the Lakeview programmatic dashboard generation engine. These constraints have been determined through API response testing, schema analysis, and error message parsing.

## 1. Top-Level Structure
- **Requirement**: The root object must contain both a `datasets` array and a `pages` array. [Verified]
- **Requirement**: A `name` string (8-character hex) is required at the root if referencing the dashboard uniquely. [Inferred]
- **Requirement**: A `warehouse_id` must be a valid SQL warehouse ID (e.g., `a1b2c3d4e5f6g7h8`). [Verified]
- **Requirement**: If updating an existing dashboard, an `etag` must be provided for optimistic locking. [Observed]

## 2. Identifiers (Names)
- **Requirement**: All `name` fields (dataset names, page names, widget names) must be strictly unique 8-character hex strings (e.g., `a1b2c3d4`). [Verified]
- **Failure Mode**: Duplicate names within a dashboard throw a `400 Bad Request` regarding ID conflicts. [Observed]

## 3. Datasets (`datasets` array)
- **Requirement**: Must contain at least one dataset if any visualization references data. [Inferred]
- **Requirement**: Each dataset must have:
  - `name`: Unique 8-char hex string. [Verified]
  - `displayName`: String, human-readable name. [Verified]
  - `query`: The SQL query string to execute. [Verified]

## 4. Pages (`pages` array)
- **Requirement**: Must contain at least one page. [Verified]
- **Requirement**: Each page must have:
  - `name`: Unique 8-char hex string. [Verified]
  - `displayName`: String, tab title. [Verified]
  - `layout`: Array of widget objects. [Verified]

## 5. Widgets (`layout` array)
- **Requirement**: Each widget in the `layout` must have a unique `name` (8-char hex). [Verified]
- **Exclusivity Rule**: A widget must have EITHER a `spec` object (for visualizations) OR a `textbox_spec` object (for text/markdown). It cannot have both. [Verified]

### 5.1. Positioning Constraints
Widgets use a 6-column grid system.
- **Rule**: `x` must be an integer, `x >= 0`. [Verified]
- **Rule**: `y` must be an integer, `y >= 0`. [Verified]
- **Rule**: `width` must be an integer, `1 <= width <= 6`. [Verified]
- **Rule**: `height` must be an integer, `height >= 1`. [Verified]
- **Rule**: `x + width <= 6`. Widgets cannot overflow the 6-column width. [Verified]
- **Overlap Rule**: No two widgets on the same page can have overlapping boundaries. (Rectangle intersection must be empty). [Observed]

### 5.2. Visualization Specifics (`spec`)
- **Requirement**: `spec.widgetType` must be a valid enum value (e.g., `table`, `bar`, `line`, `scatter`, `pie`, `counter`, `combo`). [Verified]
- **Requirement**: `spec.version` must correspond to the valid schema version for that `widgetType` category. [Observed]
- **Requirement**: All visualization queries must reference an existing dataset name via `datasetName`. [Verified]
- **Requirement**: Field expressions (e.g., in mappings) must be valid SQL. [Verified]

### 5.3. Widget Details
- **Tables**: `columns` definitions must reference fields that actually exist in the query results. [Observed]
- **Filters**: Filter widgets (if implemented) require specific `associative_filter_predicate_group` fields. [Inferred]
- **Colors**: If custom colors are used, they must be valid hex color codes (e.g., `#FF0000`). [Verified]

## 6. Serialization Validation
- **Requirement**: The `serialized_dashboard` field submitted to the API must be a valid JSON string containing the complete dashboard structure. [Verified]
