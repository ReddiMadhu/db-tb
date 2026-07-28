# Lakeview Unsupported Feature Matrix

This document details the features and functionalities currently NOT supported in Databricks Lakeview, structured as a comparative matrix against major enterprise BI platforms.

## Overview: Unsupported by Category

### Visualization Types Not Supported
- Treemaps
- Gantt Charts
- Bullet Graphs
- Waterfall Charts
- Funnel Charts
- Gauge/Dial Charts
- Sparklines (in tables)
- Custom D3.js or HTML/JS visuals

### Interaction Types Not Supported
- Highlight Actions (cross-highlighting between visuals is limited)
- Parameter Actions (dynamically updating parameters from visual clicks)
- Arbitrary Drill-through to other dashboards
- Complex Drill-down Hierarchies (expanding/collapsing nodes within a visual)

### Formatting Limitations
- Custom Shapes for scatter/line markers
- Custom Colors assigned to specific data points programmatically
- Reference Lines (static or dynamic)
- Trend Lines (linear, polynomial, etc.)
- Forecasting (built-in predictive models)
- Annotations directly on data points

### Layout & Presentation Limitations
- Floating Layouts (Lakeview strictly enforces a 6-column tiled grid)
- Device-specific Layouts (e.g., custom mobile view vs desktop view)
- Responsive reflow rules (customizing how the grid breaks on smaller screens)
- Custom Padding/Margins around widgets

### Data Feature Limitations
- Data Blending across different warehouses (must be modeled in SQL first)
- Real-time streaming data pushes (relies on SQL warehouse refresh execution)
- Incremental refresh triggered directly from the dashboard UI

### Security & Alerting
- Complex UI-driven Row-Level Security mapping (RLS must be handled in Unity Catalog or SQL views)
- Data-driven alerts generated directly from the dashboard based on thresholds

## Comparative BI Platform Matrix

| Feature | Tableau | Power BI | Looker | MicroStrategy | Qlik | SAP BO | Lakeview Support |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Treemap Visualization | Yes | Yes | Yes | Yes | Yes | Yes | **No** [Verified] |
| Gantt Chart | Yes | Yes | Yes | Yes | Yes | Yes | **No** [Verified] |
| Waterfall Chart | Yes | Yes | Yes | Yes | Yes | Yes | **No** [Verified] |
| Gauge Chart | Yes | Yes | Yes | Yes | Yes | Yes | **No** [Verified] |
| Floating Layouts | Yes | Yes | No | Yes | No | Yes | **No** (Grid only) [Verified] |
| Custom HTML/JS Vis | Yes (Ext) | Yes | Yes | Yes | Yes | Yes | **No** [Verified] |
| Parameter Actions | Yes | Yes | Yes | Yes | No | Yes | **No** [Inferred] |
| Drill-down Hierarchy | Yes | Yes | Yes | Yes | Yes | Yes | **No** [Inferred] |
| Cross-highlighting | Yes | Yes | Yes | Yes | Yes | Yes | **Limited** [Observed] |
| Reference Lines | Yes | Yes | Yes | Yes | Yes | Yes | **No** [Verified] |
| Trend Lines | Yes | Yes | Yes | Yes | Yes | Yes | **No** [Verified] |
| Forecasting | Yes | Yes | Yes | Yes | Yes | No | **No** [Verified] |
| Custom Tooltips | Yes | Yes | Yes | Yes | Yes | Yes | **No** [Observed] |
| Data-driven Alerts | Yes | Yes | Yes | Yes | Yes | Yes | **No** [Verified] |
| Device-specific Layout| Yes | Yes | No | Yes | No | No | **No** [Verified] |
| Custom Padding | Yes | Yes | No | Yes | Yes | Yes | **No** [Observed] |
| Map with Custom Polygons | Yes | Yes | Yes | Yes | Yes | Yes | **No** [Verified] |
| Annotations | Yes | Yes | No | Yes | No | Yes | **No** [Observed] |
| Data Blending (UI) | Yes | Yes | Yes | Yes | Yes | Yes | **No** (SQL only) [Inferred] |
| Complex RLS in UI | Yes | Yes | Yes | Yes | Yes | Yes | **No** (UC only) [Observed] |

*(Matrix truncated for brevity. A full enterprise assessment would contain 50+ granular features.)*
