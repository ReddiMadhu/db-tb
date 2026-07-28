# Lakeview Visualization Specification

Every claim in this document includes an evidence level: [Verified], [Observed], [Inferred], or [Hypothesized].

## Encoding Channels [Verified where seen]
- `x`: Horizontal axis dimension/measure.
- `y`: Vertical axis dimension/measure.
- `color`: Grouping or thematic coloring dimension.
- `value`: Singular metric value (e.g., in counters).
- `label`: Data labels for marks.
- `size`: [Inferred] Mark sizing for scatter or bubble charts.

## Scale Types [Verified]
- `quantitative`: Continuous numeric data.
- `temporal`: Date/time data.
- `categorical`: Discrete, unordered categories.
- `ordinal`: [Inferred] Discrete, ordered categories.

## Axis Configuration [Verified]
- `title`: Axis label customization.

## Legend Configuration [Inferred]
- Position (top, bottom, left, right, hidden), title.

## Color Palettes [Verified]
- Configured in the `mark.colors` array with string hex values.
- **Default palette (from NYC Taxi dashboard)**:
  `['#077A9D', '#FFAB00', '#00A972', '#FF3621', '#8BCAE7', '#AB4057', '#99DDB4', '#FCA4A1', '#919191', '#BF7080']`

## Label Configuration [Verified]
- `show`: boolean to toggle data labels.

## Tooltip Configuration [Inferred]
- Custom fields to show on hover, potentially defined under a `tooltip` encoding channel.

## Sorting [Inferred]
- Sort order per encoding field (e.g., ascending, descending, manual).

## Grouping [Verified]
- Primarily driven via the `color` encoding.

## Conditional Formatting [Verified]
- Supported in Table widgets (`version: 1`).
- Uses `cellFormat` object containing `rules` array.

## Number Formatting Patterns [Verified]
- Supports patterns like `'0'`, `'$0.00'`, `'0.0%'`.

## Frame Options [Verified]
- `showTitle`: boolean to display widget title.
- `title`: string for the widget title.

## Version Field Meaning [Verified]
- `1`: Table widgets and Pivot Tables.
- `2`: Counters and Filters (multi-select, single-select, date picker).
- `3`: Standard Charts (bar, scatter, line, pie, etc.).
