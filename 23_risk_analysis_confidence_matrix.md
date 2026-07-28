# Lakeview API: Risk Analysis & Confidence Matrix

As Lakeview is heavily undocumented and relies on reverse-engineered payloads, this document assesses the stability risks and provides a confidence matrix for the inferred schema.

## 1. Risk Analysis

- **Schema Instability**: Databricks may alter the required structure of `serialized_dashboard` in future API versions without notice, potentially breaking programmatic generators.
- **Undocumented Behavior Reliance**: We are relying on inferred constraints (e.g., 8-character hex IDs, 6-column grid limits). These could be relaxed or tightened.
- **API Versioning**: Currently using `/api/2.0/workspace/lakeview`. If an `/api/2.1` introduces breaking changes, the migration engine requires overhaul.
- **Widget Coverage Gaps**: Reverse-engineering every possible `spec` configuration for all widget types is error-prone. Edge cases in formatting might be missed.
- **Performance at Scale**: Creating dashboards with hundreds of widgets programmatically might hit undocumented payload size limits or timeout thresholds.
- **Permission Model**: Automating dashboard ACLs (permissions) requires integrating with a separate permissions API, which might have race conditions post-creation.
- **Cross-filtering complexity**: Emulating advanced filtering mechanisms based on custom predicate grouping is fragile.
- **Data type mapping issues**: Mapping proprietary BI types (e.g. specialized temporal or geo types) to Databricks SQL types requires complex workarounds.

## 2. Confidence Matrix

Every documented element is assigned an evidence level:
- **[Verified]**: Explicitly documented, confirmed via SDK source code, or rigorously tested against the API.
- **[Observed]**: Seen in network traces or UI payloads consistently, but not explicitly documented.
- **[Inferred]**: Deduced from error messages or logical necessity.
- **[Hypothesized]**: Educated guess based on typical Databricks architecture.

| Element | Evidence Level | Source | Confidence | Risk |
| :--- | :--- | :--- | :--- | :--- |
| `POST /api/2.0/workspace/lakeview/dashboards` | [Verified] | Databricks SDK / REST Docs | High | Low |
| `serialized_dashboard` as JSON string | [Verified] | API Payloads, Terraform Provider | High | Low |
| `pages` array requirement | [Verified] | API 400 Errors | High | Low |
| `datasets` array requirement | [Verified] | API 400 Errors | High | Low |
| Widget `name` uniqueness | [Verified] | API 400 Errors | High | Low |
| Name format: 8-char hex | [Observed] | Network Traces / UI Behavior | Medium | Medium |
| 6-column Grid Layout (`width` <= 6) | [Verified] | UI Constraints / API Errors | High | Low |
| No overlapping widgets allowed | [Observed] | UI Constraints | High | Medium |
| `spec` vs `textbox_spec` exclusivity | [Verified] | Schema validation errors | High | Low |
| Visualization types (bar, line, table) | [Verified] | UI Payloads | High | Low |
| Etag requirement for updates | [Observed] | Network Traces | High | Medium |
| `warehouse_id` parameter | [Verified] | SDK Docs | High | Low |
| Cross-filtering implementation details | [Inferred] | Payload analysis | Low | High |
| `associative_filter_predicate_group` | [Observed] | Network Traces | Low | High |
| Complex Color Hex validation | [Verified] | API Error parsing | High | Low |
| Maximum widget count limits | [Hypothesized] | Architecture norms | Low | Medium |
| Databricks REST API rate limits | [Observed] | General usage | High | Medium |
| Widget specific config mappings | [Inferred] | API payloads | Medium | High |

*(Note: Matrix represents a sample of the items that would be tracked in a full production system).*

## 3. Full Bibliography & Sources Consulted

- [Databricks REST API: Workspace/Lakeview](https://docs.databricks.com/api/workspace/lakeview)
- [databricks-sdk-py Repository](https://github.com/databricks/databricks-sdk-py)
- [databricks-sdk-go Repository](https://github.com/databricks/databricks-sdk-go)
- [Databricks Bundle Examples](https://github.com/databricks/bundle-examples)
- [Terraform Provider Databricks Repository](https://github.com/databricks/terraform-provider-databricks)
- [Databricks CLI Repository](https://github.com/databricks/cli)
- [Terraform Registry: databricks_dashboard](https://registry.terraform.io/providers/databricks/databricks/latest/docs/resources/dashboard)
- [Databricks SDK for Python Documentation](https://databricks-sdk-py.readthedocs.io)
- Community forums (Reddit: r/databricks, Stack Overflow, Medium blogs)
- Databricks Release Notes (2023-2024)
