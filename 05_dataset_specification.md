# Lakeview Dataset Specification

Every claim in this document includes an evidence level: [Verified], [Observed], [Inferred], or [Hypothesized].

## Dataset Object Schema [Verified]
- **name**: Internal identifier used for binding widgets.
- **displayName**: Human-readable name.
- **query**: The SQL query string driving the dataset.

**Example:**
```json
{
  "name": "nyc_taxi",
  "displayName": "NYC Taxi Data",
  "query": "SELECT * FROM taxi_trips"
}
```

## SQL Query Format and Constraints [Verified]
- Supports standard Spark SQL syntax.
- Constraints apply depending on the visualization type and disaggregated flags.

## Parameter Binding Syntax [Verified]
- Uses `:param_name` inside SQL queries to bind to dashboard parameters or filters.

## Widget-to-Dataset Binding [Verified]
- Binding occurs via the widget's `queries` array: `queries[].query.datasetName`.

## Field Expressions [Verified]
- **Raw Column Refs**: Just the column name, e.g., `column`.
- **Aggregations**: `COUNT(col)`, `SUM(col)`, `AVG(col)`.
- **Transforms**: `DATE_TRUNC('month', col)`.

## Disaggregated Flag [Verified]
- `disaggregated: true`: Widget expects raw rows (no GROUP BY applied automatically).
- `disaggregated: false`: Widget expects aggregated data based on encoding dimensions.

## Cross-filter Expressions [Verified]
- Special expressions like `COUNT_IF(associative_filter_predicate_group)` allow interconnected filtering across datasets.

## Query Naming [Verified]
- `'main_query'`: Typically used for main visualization widgets.
- Path-style naming: Typically used for filter widgets (e.g., `filters/borough_filter`).

## Warehouse Binding [Verified]
- Defined at the **dashboard level**, not the dataset level. Determines the compute used for the dataset's query execution.

## Caching Behavior [Inferred]
- Results are likely cached at the dataset/query level, expiring based on dashboard configuration or manual refresh.

## Schema Inference [Inferred]
- Columns and types (`quantitative`, `temporal`, `categorical`) are likely inferred directly from the underlying query result schema, eliminating the need to explicitly define dataset schemas.
