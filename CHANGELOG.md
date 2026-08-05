# Parser / Stage-2 Artifact Changelog

## 2026-08-05 — Workbook ontology extraction

New Stage-2 artifact `workbook_ontology` (and TOM enrichments) covering dashboard/datasource/worksheet detail previously missing from PARSE output.

### Added
- Workbook identity: `build_version`, `source_platform`, `repository_location`, `style_theme`, `animation_on`, `document_format_flags`, `preferences`, `mapsource`
- Datasource: `live_or_extract`, Hyper extract metadata (`hyper_file`, `rows_inserted`, `update_time`), `physical_model` (named connections + relations), `semantic_values`, `column_instances`; calc `internal_name` (`Calculation_*`)
- Dashboard: `uuid`, `sizing_mode`, `table_background`, `dash_title_style`, zone `type_v2` fidelity (`layout-basic` / `layout-flow` / `empty` / `text` / `filter` / `legend`), text-zone runs (font/size/color/bold), `layout_hierarchy`, floating vs tiled
- Worksheet: `uuid`, `map_style`, pane/table backgrounds, `mark_style`, `fixed_mark_color`, `legend_title_overrides`, `cell_formats`

### API
- `build_workbook_ontology(workbook)` → `{ "workbook_ontology": { ... } }`
- Pipeline `artifacts.workbook_ontology`

---

## 2026-08-05 — Tableau `.twb`/`.twbx` extraction correctness (Tasks 1–11)

Breaking and behavior changes for consumers of PARSE Stage-2 artifacts / `WorkbookMetadata`.

### Task 1 — Per-worksheet `measures` / `dimensions`
- **Before:** Derived from shelf `derivation` truthiness (`none:` counted as measure) with hallucination fallback to global `measures_list[:2]` / `dimensions_list[:2]`.
- **After:** Sourced only from each worksheet’s `<datasource-dependencies>/<column @role>`. Role is the sole classifier.
- **Example:** Gender Distribution → `dimensions={Demographics_Gender, StateName}`, `measures={Total Claim, Total Incidents}` (no longer hallucinates Average Age / Call Center Postal Code).

### Task 2 — Global `artifacts.measures` / `dimensions`
- **Before:** `datatype in (real, integer) or formula` → measure.
- **After:** `role='measure'|'dimension'` only.
- **Example:** Call Center Postal Code / Postal Code → dimensions; Migrated Data → measures.

### Task 3 — Worksheet `hidden`
- **Before:** Always `false` (attribute not read from `<worksheet>`).
- **After:** Read from `//windows/window[@class='worksheet']/@hidden`. Missing window → `false` + parse warning.
- **Example:** All 6 Insurance worksheets → `hidden=true`.

### Task 4 — LOD encoding channel *(breaking)*
- **Before:** `<lod>` aliased to `"channel": "detail"`.
- **After:** `"channel": "lod"`; true `<detail>` remains `"detail"`.
- **New:** `complexity.lod_channel_count` counts Marks-card `<lod>` encodings. `lod_count` still means FIXED/INCLUDE/EXCLUDE calc usage.

### Task 5 — `:Measure Names` filters
- **Before:** Skipped in filter extraction.
- **After:** Included. Workbook filter metric = sum of worksheet filter counts (Insurance = 13).

### Task 6 — Quantitative filters
- **Before:** Typed via `@type`; min/max read from attributes (missing in XML).
- **After:** `filter_type` from `@class`; `<min>`/`<max>` child elements captured.
- **Example:** Claim Paid Ratio → `quantitative`, min `0.0`, max `3.1089999999999995`.

### Task 7 — Dashboard filters vs legends *(breaking)*
- **Before:** Any zone with `param` became a filter; invented `mode: "dropdown"`.
- **After:** Only `type-v2='filter'`. Color/size/shape zones go to `dashboard_legends` / `legend_controls`.
- **Example:** Zone id `46` (Above Allowed Threshold?) is a legend, not a filter. Filters = ids `{47, 39}`.

### Task 8 — Dashboard actions *(schema addition)*
- **Before:** Actions poorly parsed / not in Stage-2 artifacts.
- **After:** Parsed from `<actions>/<action>` via `command/@command` (`tsc:tsl-filter`→filter, `tsc:brush`→highlight, …). Serialized as `artifacts.actions` with `name`, `caption`, `action_type`, `activation_type`, `target`, `field`.

### Task 9 — Groups
- **Before:** Skipped names starting with `[Exclusions`; empty `members`.
- **After:** All groups kept; `auto_column` captured; members from nested `groupfilter` tree.
- **Example:** `[Exclusions (Demographics Gender,State Name)]` included.

### Task 10 — Calculated fields
- **Before:** Missing return type / dependencies / usage.
- **After:** `return_type` (column datatype), `depends_on_fields` / artifact `dependencies`, `is_used` (shelves/encodings/filters only).

### Task 11 — Dashboard `title` *(breaking)*
- **Before:** Inferred from large/bold text-zone runs (e.g. “Insurance Claims Dashboard”).
- **After:** Only real `<title>` or `caption` attribute; otherwise `null`. Dashboard identity remains in `name` / `dashboard_name`.

### Stage-2 upload path
- Upload Stage-2 measure/dimension heuristic (keyword / datatype) replaced with the same `role`-based classification.
