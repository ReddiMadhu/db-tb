# Lakeview Layout Engine Specification

## Overview
This document specifies the layout engine used in Databricks Lakeview dashboards, defining how widgets are positioned and sized on the canvas.

## Grid System
- **6-column grid system**: [Verified] The layout uses a 6-column grid. All `x` + `width` combinations fit within the range 0-6 (Verified from NYC Taxi).
- **Position object**: [Verified] `{x, y, width, height}` — all values are integers.
- **Coordinate origin**: [Verified] Top-left is `(0,0)`.
- **Y-axis**: [Verified] Increases downward.
- **Width range**: [Verified] `1` to `6` columns.
- **Height**: [Verified] Variable rows (Heights of 1-8 rows have been observed in NYC Taxi examples).
- **No explicit row count**: [Verified] `y` values are sparse; widgets can be placed at arbitrary `y` positions without a predefined maximum row limit.

## Page Structure
- **Page Layout**: [Verified] Each page possesses an independent layout array, decoupling the layout from other pages.
- **pageType**: [Observed] Usually set to `PAGE_TYPE_CANVAS` based on community examples.

## Constraints & Behavior
- **Collision handling**: [Inferred] No overlap allowed. Widgets cannot share the same grid space.
- **Responsive behavior**: [Inferred] The dashboard uses a fixed grid. There are no responsive breakpoints implemented natively in the layout model.
- **Widget sizing constraints**: [Inferred] Minimum width of 1 column, maximum of 6 columns.

## Examples
### NYC Taxi Layout Example
[Verified]
```json
"layout": [
  { "x": 0, "y": 0, "width": 6, "height": 2 },
  { "x": 0, "y": 2, "width": 3, "height": 4 },
  { "x": 3, "y": 2, "width": 3, "height": 4 }
]
```
