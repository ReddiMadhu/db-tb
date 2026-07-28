# Lakeview Widget Specifications

Every claim in this document includes an evidence level: [Verified], [Observed], [Inferred], or [Hypothesized].

## Verified Widgets

### Bar Chart [Verified]
- **widgetType**: `'bar'`
- **version**: `3`
- **Encodings**: `x` (axis config), `y` (axis config), `color` (optional), `label`
- **Mark**: `colors` array (hex), stacking options

**Example:**
```json
{
  "widgetType": "bar",
  "version": 3,
  "queries": [{ "query": { "datasetName": "nyc_taxi", "name": "main_query" } }],
  "frame": { "showTitle": true, "title": "Trips by Borough" },
  "encoding": {
    "x": { "field": "borough", "type": "categorical", "displayName": "Borough" },
    "y": { "field": "COUNT(trip_id)", "type": "quantitative", "displayName": "Trip Count" },
    "color": { "field": "payment_type", "type": "categorical" }
  },
  "mark": {
    "colors": ["#077A9D", "#FFAB00", "#00A972"],
    "stack": "normalize"
  },
  "disaggregated": false
}
```

### Scatter Plot [Verified]
- **widgetType**: `'scatter'`
- **version**: `3`
- **Encodings**: Similar to bar (x, y, color)

**Example:**
```json
{
  "widgetType": "scatter",
  "version": 3,
  "queries": [{ "query": { "datasetName": "nyc_taxi", "name": "main_query" } }],
  "frame": { "showTitle": true, "title": "Fare vs Distance" },
  "encoding": {
    "x": { "field": "trip_distance", "type": "quantitative" },
    "y": { "field": "fare_amount", "type": "quantitative" },
    "color": { "field": "day_of_week", "type": "categorical" }
  },
  "mark": { "colors": ["#077A9D"] },
  "disaggregated": true
}
```

### Counter/KPI [Verified]
- **widgetType**: `'counter'`
- **version**: `2`
- **Encodings**: `value` (fieldName, displayName)

**Example:**
```json
{
  "widgetType": "counter",
  "version": 2,
  "queries": [{ "query": { "datasetName": "nyc_taxi", "name": "main_query" } }],
  "frame": { "showTitle": true, "title": "Total Trips" },
  "encoding": {
    "value": { "field": "COUNT(trip_id)", "displayName": "Total Trips", "format": "0,0" }
  },
  "disaggregated": false
}
```

### Table [Verified]
- **widgetType**: `'table'`
- **version**: `1`
- **Encodings**: `columns` array with full column config
- **Features**: `invisibleColumns`, `itemsPerPage`, `paginationSize`, `withRowNumber`, `condensed`, `cellFormat`

**Example:**
```json
{
  "widgetType": "table",
  "version": 1,
  "queries": [{ "query": { "datasetName": "nyc_taxi", "name": "main_query" } }],
  "frame": { "showTitle": true, "title": "Recent Trips" },
  "encoding": {
    "columns": [
      { "field": "pickup_datetime", "displayName": "Time", "type": "temporal" },
      { "field": "fare_amount", "displayName": "Fare", "type": "quantitative", "cellFormat": { "rules": [] } }
    ]
  },
  "invisibleColumns": [],
  "itemsPerPage": 50,
  "paginationSize": 5,
  "withRowNumber": true,
  "condensed": false
}
```

### Filter Multi-Select [Verified]
- **widgetType**: `'filter-multi-select'`
- **version**: `2`
- **Usage**: Cross-dataset filtering with `associative_filter_predicate_group`. Multiple queries bind to multiple datasets.

**Example:**
```json
{
  "widgetType": "filter-multi-select",
  "version": 2,
  "queries": [
    { "query": { "datasetName": "dataset1", "name": "filter_query_1" } },
    { "query": { "datasetName": "dataset2", "name": "filter_query_2" } }
  ],
  "frame": { "showTitle": true, "title": "Select Borough" },
  "encoding": { "value": { "field": "borough" } }
}
```

### Filter Date Range Picker [Verified]
- **widgetType**: `'filter-date-range-picker'`
- **version**: `2`

**Example:**
```json
{
  "widgetType": "filter-date-range-picker",
  "version": 2,
  "queries": [{ "query": { "datasetName": "nyc_taxi", "name": "date_filter" } }],
  "frame": { "showTitle": true, "title": "Date Range" },
  "encoding": { "value": { "field": "pickup_datetime" } }
}
```

### Text/Markdown (textbox_spec) [Verified]
- Simple string containing Markdown.

**Example:**
```json
{
  "textbox_spec": {
    "text": "### NYC Taxi Dashboard\nThis dashboard shows key metrics."
  }
}
```

## Inferred & Observed Widgets

### Line Chart [Inferred]
- **widgetType**: `'line'`
- **version**: `3`

### Area Chart [Inferred]
- **widgetType**: `'area'`
- **version**: `3`

### Pie/Donut Chart [Inferred]
- **widgetType**: `'pie'`
- **version**: `3`

### Combo Chart [Inferred]
- **widgetType**: `'combo'`
- **version**: `3`

### Heatmap [Inferred]
- **widgetType**: `'heatmap'`
- **version**: `3`

### Histogram [Inferred]
- **widgetType**: `'histogram'`
- **version**: `3`

### Map [Inferred]
- **widgetType**: `'map'`
- **version**: `3`

### Pivot Table [Inferred]
- **widgetType**: `'pivot'`
- **version**: `1`

### Filter Single Select [Inferred]
- **widgetType**: `'filter-single-select'`
- **version**: `2`

### Image [Observed]
- **widgetType**: `'image'`
