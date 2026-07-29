# Phase 8: Complete Visualization Mapping

This document provides an exhaustive, implementation-level guide to mapping Tableau visualization types to Databricks Lakeview widgets. It is designed to allow a team of engineers to build a production translation engine without additional research.

## 1. Encoding Channel Mapping

| Tableau Shelf/Channel | Lakeview Encoding | Support Status | Notes |
|---|---|---|---|
| Columns (dimension) | `encodings.x` | Supported | Base x-axis mapping |
| Rows (measure) | `encodings.y` | Supported | Base y-axis mapping |
| Color | `encodings.color` | Supported | Maps to grouping or color scale |
| Size | NOT SUPPORTED | Unsupported | Lakeview lacks mark size encoding |
| Shape | NOT SUPPORTED | Unsupported | Lakeview lacks shape encoding |
| Label | `encodings.label` | Supported | Text labels on marks |
| Tooltip | NOT DIRECTLY SUPPORTED | Unsupported | Lakeview tooltips are auto-generated based on encoded fields |
| Detail | Additional GROUP BY | Supported | Handled in the underlying dataset query |
| Path | NOT SUPPORTED | Unsupported | Drawing custom paths/polygons is not supported |
| Angle (pie) | `encodings.y` | Supported | Defines the arc size in pie/donut charts |

## 2. Mark Property Translation

- **Color**: Tableau color palettes can be translated into the Lakeview `mark.colors` hex array.
- **Opacity**: NOT SUPPORTED. Workaround is to pre-bake colors with alpha in hex strings if Lakeview UI supports it, but natively opacity control is not exposed.
- **Border**: NOT SUPPORTED.
- **Size**: NOT SUPPORTED for encodings.
- **Shape**: NOT SUPPORTED.
- **Stacking**: Handled via `encodings.color` + chart specification (e.g., stacked bar chart widget type).

## 3. Formatting Translation

- **Axis Formatting**: Translated to `axis.title` and axis label settings in Lakeview if exposed, else handled in query aliases.
- **Number Format**: Translated to `numberFormat` at the dataset column level in Lakeview.
- **Date Format**: Requires expression-level formatting in the underlying SQL query (e.g., `DATE_FORMAT(date_col, 'yyyy-MM-dd')`).
- **Reference Lines**: NOT SUPPORTED. Workaround: Include a dual-axis line or hardcode in the dataset.
- **Trend Lines**: NOT SUPPORTED.
- **Annotations**: NOT SUPPORTED.
- **Grid Lines**: NOT CONFIGURABLE in Lakeview (auto-managed by the platform).

---

## 4. Visualization Mapping Details

### 4.1. Bar Chart (Vertical, Horizontal, Stacked, Grouped, 100%)

**Tableau Configuration:**
- Shelves: Columns (Dimension), Rows (Measure)
- Mark Type: Bar
- Encodings: Color (for stacked/grouped)

**Lakeview Equivalent:**
- widgetType: `bar`
- spec.version: `1`

**Encoding Translation:**
- Columns (Dim) -> `encodings.x`
- Rows (Measure) -> `encodings.y`
- Color -> `encodings.color` (defines grouping/stacking)

**Limitations:**
- Variable bar width based on measure is not supported.

**Workarounds:**
- 100% stacked bar: Requires pre-computing percentages in the SQL dataset.

**Complete JSON Example:**
```json
{
  "widgetType": "bar",
  "spec": {
    "version": 1,
    "dataset": "dataset_id_123",
    "encodings": {
      "x": { "field": "category", "type": "NOMINAL" },
      "y": { "field": "sales", "type": "QUANTITATIVE", "aggregate": "SUM" },
      "color": { "field": "region", "type": "NOMINAL" }
    },
    "config": {
      "stack": true
    }
  }
}
```

### 4.2. Line Chart

**Tableau Configuration:**
- Shelves: Columns (Date/Dimension), Rows (Measure)
- Mark Type: Line
- Encodings: Color (Multiple Lines)

**Lakeview Equivalent:**
- widgetType: `line`
- spec.version: `1`

**Encoding Translation:**
- Columns (Date) -> `encodings.x`
- Rows (Measure) -> `encodings.y`
- Color -> `encodings.color`

**Limitations:**
- Step and jump lines are not natively supported.
- Path encoding to reorder points is unsupported.

**Workarounds:**
- Pre-sort data in the SQL query for correct line rendering if x-axis is not naturally ordered.

**Complete JSON Example:**
```json
{
  "widgetType": "line",
  "spec": {
    "version": 1,
    "dataset": "dataset_id_123",
    "encodings": {
      "x": { "field": "order_date", "type": "TEMPORAL" },
      "y": { "field": "revenue", "type": "QUANTITATIVE" },
      "color": { "field": "product_line", "type": "NOMINAL" }
    }
  }
}
```

### 4.3. Area Chart

**Tableau Configuration:**
- Shelves: Columns (Dimension), Rows (Measure)
- Mark Type: Area
- Encodings: Color

**Lakeview Equivalent:**
- widgetType: `area`
- spec.version: `1`

**Encoding Translation:**
- Columns -> `encodings.x`
- Rows -> `encodings.y`
- Color -> `encodings.color`

**Limitations:**
- 100% stacked area requires SQL pre-computation.

**Workarounds:**
- Compute percentage of total across the partition in SQL.

**Complete JSON Example:**
```json
{
  "widgetType": "area",
  "spec": {
    "version": 1,
    "dataset": "dataset_id_123",
    "encodings": {
      "x": { "field": "month", "type": "TEMPORAL" },
      "y": { "field": "profit", "type": "QUANTITATIVE" },
      "color": { "field": "department", "type": "NOMINAL" }
    }
  }
}
```

### 4.4. Scatter Plot

**Tableau Configuration:**
- Shelves: Columns (Measure), Rows (Measure)
- Mark Type: Circle/Shape
- Encodings: Detail (Dimension), Color

**Lakeview Equivalent:**
- widgetType: `scatter`
- spec.version: `1`

**Encoding Translation:**
- Columns -> `encodings.x`
- Rows -> `encodings.y`
- Color -> `encodings.color`
- Detail -> Implicitly handled by row-level data

**Limitations:**
- No trend lines.
- No size encoding for bubbles.
- No shape encoding.

**Workarounds:**
- Pre-calculate trend line points and use a dual-axis chart if supported, or just omit.

**Complete JSON Example:**
```json
{
  "widgetType": "scatter",
  "spec": {
    "version": 1,
    "dataset": "dataset_id_123",
    "encodings": {
      "x": { "field": "marketing_spend", "type": "QUANTITATIVE" },
      "y": { "field": "sales", "type": "QUANTITATIVE" },
      "color": { "field": "region", "type": "NOMINAL" }
    }
  }
}
```

### 4.5. Pie / Donut Chart

**Tableau Configuration:**
- Shelves: None
- Mark Type: Pie
- Encodings: Angle (Measure), Color (Dimension)

**Lakeview Equivalent:**
- widgetType: `pie` (or `donut`)
- spec.version: `1`

**Encoding Translation:**
- Angle -> `encodings.y`
- Color -> `encodings.color`

**Limitations:**
- Donut charts in Tableau use dual-axis workarounds. Lakeview might natively support donut configurations via properties.

**Workarounds:**
- Direct translation to Pie widget.

**Complete JSON Example:**
```json
{
  "widgetType": "pie",
  "spec": {
    "version": 1,
    "dataset": "dataset_id_123",
    "encodings": {
      "y": { "field": "sales", "type": "QUANTITATIVE" },
      "color": { "field": "category", "type": "NOMINAL" }
    }
  }
}
```

### 4.6. Text Table (Crosstab)

**Tableau Configuration:**
- Shelves: Columns (Dimension), Rows (Dimension)
- Mark Type: Text
- Encodings: Text (Measure)

**Lakeview Equivalent:**
- widgetType: `table` (or `pivot_table`)
- spec.version: `1`

**Encoding Translation:**
- Map dimensions to group-by or pivot columns.
- Map measures to cell values.

**Limitations:**
- Advanced formatting and sub-totals might not have 1:1 parity.

**Workarounds:**
- Replicate sub-totals via SQL ROLLUP if native support is missing.

**Complete JSON Example:**
```json
{
  "widgetType": "table",
  "spec": {
    "version": 1,
    "dataset": "dataset_id_123",
    "columns": [
      { "field": "region", "type": "NOMINAL" },
      { "field": "category", "type": "NOMINAL" },
      { "field": "sales", "type": "QUANTITATIVE", "format": "currency" }
    ]
  }
}
```

### 4.7. Highlight Table / Heatmap

**Tableau Configuration:**
- Shelves: Columns, Rows
- Mark Type: Square
- Encodings: Color (Measure), Text (Measure)

**Lakeview Equivalent:**
- widgetType: `heatmap`
- spec.version: `1`

**Encoding Translation:**
- Columns -> `encodings.x`
- Rows -> `encodings.y`
- Color Measure -> `encodings.color`

**Limitations:**
- Size variation in heatmaps is unsupported.

**Complete JSON Example:**
```json
{
  "widgetType": "heatmap",
  "spec": {
    "version": 1,
    "dataset": "dataset_id_123",
    "encodings": {
      "x": { "field": "month", "type": "NOMINAL" },
      "y": { "field": "region", "type": "NOMINAL" },
      "color": { "field": "sales", "type": "QUANTITATIVE" }
    }
  }
}
```

### 4.8. Histogram

**Tableau Configuration:**
- Shelves: Columns (Bin), Rows (Count)

**Lakeview Equivalent:**
- widgetType: `histogram`
- spec.version: `1`

**Encoding Translation:**
- Measure -> `encodings.x` (Lakeview handles binning).

**Complete JSON Example:**
```json
{
  "widgetType": "histogram",
  "spec": {
    "version": 1,
    "dataset": "dataset_id_123",
    "encodings": {
      "x": { "field": "age", "type": "QUANTITATIVE" }
    },
    "config": { "bins": 10 }
  }
}
```

### 4.9. KPI / Big Number

**Tableau Configuration:**
- Shelves: Text (Measure)

**Lakeview Equivalent:**
- widgetType: `counter`
- spec.version: `1`

**Encoding Translation:**
- Text -> `encodings.value`

**Complete JSON Example:**
```json
{
  "widgetType": "counter",
  "spec": {
    "version": 1,
    "dataset": "dataset_id_123",
    "encodings": {
      "value": { "field": "total_sales", "type": "QUANTITATIVE", "aggregate": "SUM" }
    }
  }
}
```

### 4.10. UNSUPPORTED Visualizations

The following Tableau visualizations have no direct equivalent in Lakeview and require workarounds:

| Visualization | Limitation | Workaround |
|---|---|---|
| Treemap | No native widget | Fallback to Bar Chart or Pivot Table |
| Gantt Chart | No native widget | Fallback to Table or distinct horizontal bars |
| Bullet Chart | No native widget | Fallback to Bar Chart with reference metrics in text |
| Packed Bubbles | No native widget | Fallback to Bar Chart or Pie Chart |
| Waterfall Chart | No native widget | Fallback to Bar Chart with pre-computed running totals |
| Funnel Chart | No native widget | Fallback to Bar Chart sorted descending |
| Gauge Chart | No native widget | Fallback to KPI / Counter widget |
| Sparkline | No native widget | Fallback to Line Chart |
