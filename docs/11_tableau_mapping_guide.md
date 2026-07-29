# Tableau to Databricks Lakeview Mapping Guide

This guide provides an exhaustive mapping from Tableau constructs to Databricks Lakeview equivalents. It serves as a blueprint for migrating BI assets.

## Data Layer [Verified]

| Tableau Construct | Lakeview Equivalent | Support | Notes |
|---|---|---|---|
| Data Source (.tds/.tdsx) | Dataset (SQL query) | ✅ Full | Rewrite connection as SQL SELECT |
| Extract (.hyper) | Materialized View / SQL query | ✅ Full | Pre-compute via MV |
| Live Connection | Dataset SQL query | ✅ Full | Direct SQL |
| Custom SQL | Dataset query field | ✅ Full | Direct mapping |
| Calculated Field | SQL expression in field | ✅ Full | Rewrite in SQL syntax |
| LOD Expression (FIXED/INCLUDE/EXCLUDE) | SQL subquery/window function | ⚠️ Manual | Requires SQL rewrite |
| Table Calculation | SQL window function | ⚠️ Manual | Requires SQL rewrite |
| Parameter | Filter widget or SQL :param | ⚠️ Partial | Limited to filter types |
| Set | SQL WHERE clause / CTE | ✅ Full | Rewrite as SQL |
| Group | SQL CASE WHEN or GROUP BY | ✅ Full | Rewrite |
| Bin | SQL expression (FLOOR/CEIL) | ✅ Full | Rewrite |
| Date Part | DATE_TRUNC/EXTRACT SQL | ✅ Full | Direct SQL |
| Blend | SQL JOIN in dataset | ✅ Full | Join in query |

## Visualization Layer [Observed]

| Tableau Viz | Lakeview Widget | Support | Notes |
|---|---|---|---|
| Bar Chart | bar (version 3) | ✅ Full | |
| Stacked Bar | bar + color encoding | ✅ Full | |
| Line Chart | line (version 3) | ✅ Full | |
| Area Chart | area (version 3) | ✅ Full | |
| Scatter Plot | scatter (version 3) | ✅ Full | |
| Pie Chart | pie (version 3) | ✅ Full | |
| Treemap | Not available | ❌ None | Use table instead |
| Heatmap | heatmap (version 3) | ✅ Full | |
| Histogram | histogram (version 3) | ✅ Full | |
| Box Plot | boxplot (version 3) | ✅ Full | |
| Gantt Chart | Not available | ❌ None | |
| Bullet Graph | Not available | ❌ None | |
| Text Table | table (version 1) | ✅ Full | |
| Highlight Table | table + cellFormat | ⚠️ Partial | Limited conditional formatting |
| Map (filled) | map (version 3) | ⚠️ Limited | Basic choropleth |
| Map (symbol) | map (version 3) | ⚠️ Limited | Point maps |
| Dual Axis | combo (version 3) | ⚠️ Partial | Bar+line combo |
| Reference Lines | Not available | ❌ None | |
| Trend Lines | Not available | ❌ None | |
| Forecast | Not available | ❌ None | |
| KPI / Big Number | counter (version 2) | ✅ Full | |

## Dashboard/Layout Layer [Inferred]

| Tableau | Lakeview | Support | Notes |
|---|---|---|---|
| Dashboard | Dashboard (pages array) | ✅ Full | |
| Sheet on Dashboard | Widget in layout | ✅ Full | |
| Story | Multi-page dashboard | ⚠️ Partial | Pages ≈ Story points |
| Horizontal Container | Grid columns (position.x) | ⚠️ Different | Absolute grid vs flex |
| Vertical Container | Grid rows (position.y) | ⚠️ Different | |
| Tiled Layout | 6-column grid | ⚠️ Different | Must calculate positions |
| Floating Layout | Not available | ❌ None | Only grid positioning |
| Device Layouts | Not available | ❌ None | No responsive |
| Padding/Margins | Not available | ❌ None | Grid handles spacing |

## Interaction Layer [Hypothesized]

| Tableau | Lakeview | Support | Notes |
|---|---|---|---|
| Quick Filter | filter-multi-select / filter-single-select | ✅ Full | |
| Date Filter | filter-date-range-picker | ✅ Full | |
| Filter Action | Cross-filtering (associative) | ⚠️ Partial | Automatic, less control |
| Highlight Action | Not available | ❌ None | |
| URL Action | Not available natively | ❌ None | Use linkUrlTemplate in table |
| Go to Sheet Action | Not available | ❌ None | |
| Parameter Action | Not available | ❌ None | |

## Migration Strategy

The recommended migration process [Verified] from Tableau to Lakeview involves the following steps:
1. **Parse**: Read the `.twb` XML to extract data sources, worksheets, and dashboard layouts.
2. **Convert calculations**: Map Tableau calculated fields to standard Databricks SQL.
3. **Map visuals**: Map each worksheet to a Lakeview dataset + widget.
4. **Layout translation**: Calculate 6-column grid positions from Tableau's container-based (or absolute floating) coordinates.
5. **Serialize**: Generate the `serialized_dashboard` JSON payload for Lakeview.
6. **Publish**: Create the dashboard via API or Databricks Asset Bundles.
7. **Deploy**: Push changes.

Note: Databricks provides a built-in `/importBI` command for Genie Code that assists in some metadata extraction.
