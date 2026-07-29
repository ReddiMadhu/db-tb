# Databricks Lakeview API: Unknown & Internal Fields

This document details the observed, verified, and hypothesized internal fields and undocumented behaviors within the Databricks Lakeview API and serialized dashboard definitions.

## 1. Virtual & Injected Fields

| Field / Concept | Evidence Level | Description |
| :--- | :--- | :--- |
| `associative_filter_predicate_group` | [Verified] | Virtual column injected by the runtime for cross-filtering. Observed in the NYC Taxi dashboard for cross-filtering interactions between widgets. |
| **Query Name Format** | [Verified] | Format: `dashboards/{dashboard_uuid}/datasets/{dataset_uuid}_{field_name}`. Used for filter binding. |

## 2. Identifier Formats

| Identifier | Evidence Level | Format / Description |
| :--- | :--- | :--- |
| **Widget Name** | [Verified] | 8-character hex string (e.g., `a1b2c3d4`). Appears to be a truncated UUID. |
| **Dataset Name** | [Verified] | 8-character hex string (e.g., `e5f6g7h8`). Appears to be a truncated UUID. |
| **Page Name** | [Verified] | 8-character hex string (e.g., `i9j0k1l2`). Appears to be a truncated UUID. |

## 3. Specification & UI Flags

| Field Path | Evidence Level | Description / Values |
| :--- | :--- | :--- |
| `spec.version` | [Verified] | Defines widget type. Based on patterns: `1` = Table/Pivot, `2` = Counter/Filter, `3` = Chart. |
| `uiSettings.genieSpace` | [Observed] | Configuration related to the Genie AI assistant integration within the dashboard space. |
| `disaggregated` | [Verified] | Boolean. `true` = return raw rows, `false` = apply aggregation defined in fields. |
| `mark.colors` | [Verified] | Array defining the color palette used for chart marks. |
| `frame.showTitle` | [Verified] | Boolean. Controls visibility of the widget title. |
| `frame.title` | [Verified] | String. The text of the widget title. |
| `cellFormat.rules[].if.fn` | [Verified] | Function name for conditional formatting comparison operators (e.g., `>`, `<`, `==`). |
| `invisibleColumns` | [Verified] | Array of column names to hide in a table widget. Observed in NYC Taxi dashboard. |
| `condensed` | [Verified] | Boolean. Enables compact table mode. |
| `paginationSize` | [Verified] | Controls table pagination. Values: `'default'` or a specific number. |

## 4. Unknowns & Future Discoveries

The following areas require live network capture (HAR) or direct API introspection to fully document:
- Complete list of `spec.version` mappings.
- Full schema of `uiSettings.genieSpace`.
- Any rate-limiting headers or internal telemetry fields sent during dashboard interaction.
- Fields that may exist for advanced configurations (e.g., custom maps, advanced geographic configurations) not present in the NYC Taxi example.
- Structure of the `associative_filter_predicate_group` when nested in complex AND/OR filter logic.
