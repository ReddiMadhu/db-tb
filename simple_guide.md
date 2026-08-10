# How the Migration Engine Works — Simple Guide

> This guide explains in plain language what happens inside the migration engine,
> with pointers to the actual code files that do the work.

---

## Part 1: How Calculated Fields Get Converted

### What is a Calculated Field?

In Tableau, a **calculated field** is a formula you write to create new data that doesn't exist in your original table. For example:

- **Approval Rate** = `COUNT(approved claims) / COUNT(all claims)`
- **Is High Priority** = `IF [Duration] > 30 THEN "Yes" ELSE "No" END`
- **Claims Per Province** = `{FIXED [Province] : COUNTD([Claim CaseNumber])}`

Databricks doesn't understand Tableau's formula language. So the engine **translates** each formula into Databricks SQL — like translating English to Spanish.

---

### How Translation Works (Step by Step)

**The code that does this lives in:**
[expression_compiler.py](file:///c:/Users/madhu/Desktop/db-tb/src/app/services/compiler/expression_compiler.py)

The main function is `compile_expression_to_sql()`. It takes a Tableau formula as input and returns Databricks SQL as output.

#### Step 1: Check for LOD Expressions (Level of Detail)

LOD expressions are Tableau's way of calculating at a different granularity than what's shown on screen.

**Tableau writes:**
```
{FIXED [Province] : COUNT(DISTINCT [Claim CaseNumber])}
```
This means: "Count unique claims per province, regardless of what else is on the chart."

**The engine converts it to:**
```sql
(SELECT _lod._lod_val FROM (
  SELECT `Province` AS _lod_dim_0,
         COUNT(DISTINCT `Claim CaseNumber`) AS _lod_val
  FROM _src
  GROUP BY `Province`
) _lod WHERE _lod._lod_dim_0 = `Province`)
```

**What happened:** The engine created a mini-query that groups by Province, counts the claims, and joins the result back. This is how databases achieve the same "fixed level" concept.

**Code location:** Lines 67–97 in expression_compiler.py — the function `_compile_lod_fixed()`.

---

#### Step 2: Convert IF/THEN/ELSE to CASE WHEN

Tableau uses `IF...THEN...ELSE...END`. Databricks SQL uses `CASE WHEN...THEN...ELSE...END`.

**Tableau writes:**
```
IF [Benefit Status] = "Approved" THEN "Yes"
ELSEIF [Benefit Status] = "Denied" THEN "No"
ELSE "Pending"
END
```

**The engine converts it to:**
```sql
CASE WHEN `Benefit Status` = "Approved" THEN "Yes"
     WHEN `Benefit Status` = "Denied" THEN "No"
     ELSE "Pending"
END
```

**What happened:** `IF` became `CASE WHEN`, `ELSEIF` became `WHEN`, and square brackets `[Field]` became backticks `` `Field` `` (Databricks style).

**Code location:** Lines 129–175 — the function `_compile_if_to_case()`.

---

#### Step 3: Swap Tableau Functions for Databricks Equivalents

Tableau and Databricks have many of the same functions but with different names. The engine has a **translation dictionary** of 120+ functions.

**Examples:**

| You write in Tableau | Engine converts to Databricks SQL |
|---------------------|----------------------------------|
| `COUNTD([Customer])` | `COUNT(DISTINCT \`Customer\`)` |
| `ZN([Sales])` | `COALESCE(\`Sales\`, 0)` |
| `LEN([Name])` | `LENGTH(\`Name\`)` |
| `FIND([Text], "abc")` | `LOCATE("abc", \`Text\`)` ← arguments swapped! |
| `TODAY()` | `CURRENT_DATE()` |
| `ISNULL([Field])` | `\`Field\` IS NULL` |
| `DATEDIFF('day', [Start], [End])` | `DATEDIFF(\`End\`, \`Start\`)` ← arguments swapped! |
| `MEDIAN([Value])` | `PERCENTILE(\`Value\`, 0.5)` |

**Code location:** The dictionary is in [function_mapping.py](file:///c:/Users/madhu/Desktop/db-tb/src/app/services/compiler/function_mapping.py). The regex-based replacements are in lines 183–369 of expression_compiler.py — function `_apply_function_mappings()`.

---

#### Step 4: Convert Field References

Tableau uses `[Square Brackets]` around field names. Databricks uses `` `Backticks` ``.

**Tableau:** `SUM([Business Days Duration])`
**Databricks:** `` SUM(`Business Days Duration`) ``

**Code location:** Line 56 — function `_bracket_to_backtick()`.

---

#### Step 5: Make Division Safe

Tableau silently handles division by zero. Databricks throws an error. The engine wraps every division to be safe.

**Tableau:** `SUM([Approved]) / SUM([Total])`
**Databricks (made safe):**
```sql
CAST((SUM(`Approved`)) AS DOUBLE) / NULLIF((SUM(`Total`)), 0)
```

- `CAST(... AS DOUBLE)` prevents integer division (which would give 0 instead of 0.75)
- `NULLIF(..., 0)` returns NULL instead of crashing when dividing by zero

**Code location:** Lines 506–558 — function `_coerce_division_to_double()`.

---

### Real Example from Claims Overview

The **Approval Rate** calculated field in the golden JSON:

```json
{
  "name": "approval_rate",
  "expr": "COUNT(CASE WHEN `Benefit Status` = 'Approved' THEN `Claim CaseNumber` END) * 1.0 / COUNT(`Claim CaseNumber`)"
}
```

**What the engine did:**
1. Took the Tableau formula for approval rate
2. Converted the `IF` condition to `CASE WHEN`
3. Changed brackets to backticks
4. Multiplied by `1.0` to ensure decimal division (not integer)
5. Produced a valid Databricks SQL expression

---

### Confidence Scoring

The engine tells you how confident it is in each translation:

| Confidence | Meaning |
|-----------|---------|
| **0.90** (RULE) | Used a known translation rule — high confidence |
| **0.88** (RULE) | Formula was already valid SQL — just changed brackets to backticks |
| **0.85** (RULE) | Table calculation converted to window function — good but verify |
| **0.50** (FALLBACK) | No rule matched — might need manual review or LLM assistance |

---

---

## Part 2: How Worksheets Get Converted

### What is a Worksheet?

A Tableau **worksheet** is a single chart or table. It has:
- A **data source** (which table to query)
- **Dimensions** on shelves (categories like Province, Diagnosis)
- **Measures** on shelves (numbers like SUM of Claims)
- A **mark type** (bar, line, pie, text, etc.)
- **Filters** (only show certain data)
- **Color/size/label** encodings (visual styling)

The engine converts each worksheet into a **Lakeview widget** (a visual component in Databricks).

---

### How Worksheet Conversion Works (Step by Step)

**The code that does this lives in:**
[tom_to_ubim.py](file:///c:/Users/madhu/Desktop/db-tb/src/app/services/normalizer/tom_to_ubim.py) — 2,443 lines, the largest file in the project.

#### Step 1: Figure Out the Chart Type

The engine reads the Tableau mark type (bar, line, text, circle, etc.) and decides what kind of Lakeview widget to create.

**Code:** [mark_type_resolver.py](file:///c:/Users/madhu/Desktop/db-tb/src/app/services/parser/mark_type_resolver.py)

**Simple rules:**
- Tableau `bar` → Lakeview `bar` chart
- Tableau `line` → Lakeview `line` chart
- Tableau `pie` → Lakeview `pie` chart
- Tableau `circle` → Lakeview `scatter` plot
- Tableau `text` with only one measure and no categories → Lakeview `counter` (KPI card)
- Tableau `text` with categories → Lakeview `table`
- Tableau `automatic` with dates → Lakeview `line` chart
- Tableau `map` → Lakeview `table` (maps not supported, converted to table)

**Real example:** The "Total Claims" worksheet in Claims Overview uses a text mark with a single COUNTD measure and no dimension shelves → detected as **KPI** → becomes a `counter` widget.

---

#### Step 2: Find the Right Data Source

Each worksheet is connected to a datasource. The engine finds it by matching the worksheet's `datasource_name` to the list of datasources in the workbook.

**Code:** Function `_resolve_datasource()` in tom_to_ubim.py (line 168).

**For Claims Overview:** The worksheet connects to `claims_fact` → the engine finds `DatasourceMetadata` for that name → discovers it has tables `claims_fact`, `benefit_type_dim`, `occupation_dim`.

---

#### Step 3: Read What's on the Shelves

Tableau shelves tell the engine what data goes where:

| Shelf | Example | What it means |
|-------|---------|--------------|
| **Columns** | `qr:Benefit Creation Date` | X-axis = quarter of Benefit Creation Date |
| **Rows** | `cntd:Claim CaseNumber` | Y-axis = count distinct of Claim CaseNumber |
| **Color** | `Benefit Type Group` | Color series = Benefit Type Group |
| **Filter** | `Benefit Status` = 'Closed' | Only show closed claims |

The prefix tells the engine what aggregation to use:
- `sum:` → SUM()
- `avg:` → AVG()
- `cntd:` → COUNT(DISTINCT)
- `qr:` → QUARTER() (date truncation)
- `yr:` → YEAR()

---

#### Step 4: Build the SQL Query

The engine constructs a SQL query for each worksheet:

```sql
SELECT
    QUARTER(`Benefit Creation Date`) AS benefit_creation_date_quarter,  -- from Columns shelf
    `Benefit Type Group` AS benefit_type_group,                         -- from Color encoding
    COUNT(DISTINCT `Claim CaseNumber`) AS total_claims                 -- from Rows shelf
FROM hive_metastore.insurance_data.claims_fact                          -- from datasource mapping
WHERE `Benefit Status` IN ('Closed')                                    -- from filter
GROUP BY
    QUARTER(`Benefit Creation Date`),
    `Benefit Type Group`
ORDER BY total_claims DESC                                              -- from sort
```

**What each part comes from:**
- `SELECT` columns → shelves + encodings (dimensions and measures)
- `FROM` table → datasource mapping to Unity Catalog FQN
- `WHERE` → worksheet filters
- `GROUP BY` → all dimensions (non-aggregated columns)
- `ORDER BY` → worksheet sorts

---

#### Step 5: Create the Intermediate Widget

The engine creates an `IntermediateWidget` — a platform-neutral description of the visual:

```
IntermediateWidget:
  chart_type: BAR
  dataset_name: "benefit_type_claims_ds"
  encodings:
    - X: benefit_creation_date_quarter (categorical)
    - Y: total_claims (quantitative, SUM)
    - COLOR: benefit_type_group (categorical)
  query_fields:
    - {name: "benefit_creation_date_quarter", expr: "QUARTER(`Benefit Creation Date`)"}
    - {name: "benefit_type_group", expr: "`Benefit Type Group`"}
    - {name: "total_claims", expr: "COUNT(DISTINCT `Claim CaseNumber`)"}
  title: "Benefit Type Claims"
  position: {x: 0, y: 2, width: 6, height: 4}
```

This is the **Universal BI Model (UBIM)** — it describes what the chart should show without being tied to either Tableau or Databricks.

---

### Real Example: All Claims Overview Worksheets

| Tableau Worksheet | Detected Type | Lakeview Widget | What it Shows |
|------------------|---------------|-----------------|---------------|
| Total Claims | KPI (text, 1 measure) | `counter` | Single number: COUNT(DISTINCT claims) |
| Average Duration | KPI + filter (Closed) | `counter` | Single number: AVG(duration) for closed claims |
| Approval Rate | KPI (calculated field) | `counter` | Single number: approved/total ratio |
| Benefit Type Claims | Bar (stacked, color by type) | `bar` (stacked) | Bar chart: claims by quarter, colored by benefit type |
| Diagnosis Trends | Line (color by diagnosis) | `line` | Line chart: top 4 diagnoses over time |
| Closed Claims Table | Text table + filter | `table` | Data table: sorted by duration DESC, filtered to Closed |

---

---

## Part 3: How the Lakeview JSON Gets Generated

### What is the Lakeview JSON?

The **Lakeview JSON** is the file that Databricks reads to display your dashboard. It's like a recipe:
- **Datasets** = "Here's the data and how to query it"
- **Pages** = "Here are the pages of the dashboard"
- **Widgets** = "Here are the charts/tables/KPIs on each page"
- **Positions** = "Here's where each widget sits on the grid"

---

### How JSON Generation Works (Step by Step)

**The code that does this lives in:**
[lakeview_generator.py](file:///c:/Users/madhu/Desktop/db-tb/src/app/services/generator/lakeview_generator.py)

The main function is `generate_lakeview_dashboard()` (line 662).

#### Step 1: Create Datasets

For each data query (from Step 4 above), the engine creates a **dataset**:

```json
{
  "name": "a3f2b8c1",
  "displayName": "Benefit Type Claims",
  "query": "SELECT QUARTER(`Benefit Creation Date`) AS ..., COUNT(DISTINCT `Claim CaseNumber`) AS ... FROM hive_metastore.insurance_data.claims_fact GROUP BY ..."
}
```

The `name` is a unique 8-character ID generated deterministically (same input always gives same ID).

**Code:** Lines 669–677 in lakeview_generator.py.

> **Note about the Golden JSON:** The golden Claims Overview file uses a more advanced format called the **semantic dataset layer** instead of raw SQL. It looks like this:

```json
{
  "name": "claims_overview",
  "displayName": "Claims Overview",
  "config": {
    "source": "SELECT cf.* FROM hive_metastore.insurance_data.claims_fact cf JOIN (...)",
    "measures": [
      {"name": "total_claims", "expr": "COUNT(DISTINCT `Claim CaseNumber`)"}
    ],
    "dimensions": [
      {"name": "province", "expr": "`Province`"}
    ],
    "joins": [
      {"name": "benefit_type_dim", "source": "hive_metastore.insurance_data.benefit_type_dim", "on": "..."}
    ]
  }
}
```

> In this format, measures and dimensions are **named** and widgets reference them by name (e.g., `MEASURE(\`total_claims\`)`). The migration engine currently produces raw SQL datasets, but the golden shows the richer semantic format.

---

#### Step 2: Create Pages

Each Tableau dashboard becomes a **page** in Lakeview:

```json
{
  "name": "insurance_claims_overview",
  "displayName": "Insurance Claims Overview",
  "layout": [ ... widgets go here ... ],
  "pageType": "PAGE_TYPE_CANVAS",
  "layoutVersion": "GRID_V1"
}
```

The Claims Overview golden has **2 pages**:
1. "Insurance Claims Overview" — the main view
2. "Claims Overview by Diagnosis" — filtered detail view

**Code:** Lines 679–684 in lakeview_generator.py.

---

#### Step 3: Position Widgets on the Grid

Lakeview uses a **grid layout**. Each widget has a position:

```json
"position": {
  "x": 0,        // column position (0 = left edge)
  "y": 0,        // row position (0 = top)
  "width": 4,    // how many columns wide
  "height": 2    // how many rows tall
}
```

The golden uses a **12-column grid**. The engine's layout engine places widgets to fill the page:

| Widget | Position | Size | Visual Placement |
|--------|----------|------|-----------------|
| Total Claims | x:0, y:0 | 4×2 | Top-left third |
| Avg Duration | x:4, y:0 | 4×2 | Top-center third |
| Approval Rate | x:8, y:0 | 4×2 | Top-right third |
| Diagnosis Trends | x:0, y:2 | 4×6 | Middle-left |
| Benefit Type Claims | x:4, y:2 | 8×6 | Middle-right (wider) |
| Closed Claims Table | x:0, y:8 | 12×6 | Full-width bottom |

**Code:** [layout_engine.py](file:///c:/Users/madhu/Desktop/db-tb/src/app/services/generator/layout_engine.py) — function `project_to_6column_grid()`.

---

#### Step 4: Build Each Widget

This is where the **WidgetFactory** comes in. It's the single authority on how every chart type should be structured.

**Code:** [widget_factory.py](file:///c:/Users/madhu/Desktop/db-tb/src/app/services/generator/widget_factory.py)

##### Counter / KPI Widget (Total Claims)

The factory builds:
```json
{
  "name": "total_claims",
  "queries": [{
    "name": "main_query",
    "query": {
      "datasetName": "claims_overview",
      "fields": [{"name": "measure(total_claims)", "expression": "MEASURE(`total_claims`)"}],
      "disaggregated": false
    }
  }],
  "spec": {
    "version": 2,
    "widgetType": "counter",
    "frame": {"title": "Total Claims", "showTitle": true},
    "encodings": {
      "value": {"fieldName": "measure(total_claims)"}
    },
    "data": {"queryName": "main_query"}
  }
}
```

**What each piece means:**
- `queries` → tells Databricks which dataset to query and what fields to fetch
- `spec.widgetType: "counter"` → display as a big single number
- `spec.version: 2` → counters must use version 2 (factory rule)
- `encodings.value` → which field to display as the big number
- `data.queryName` → links the visual to the query

**Factory code:** `WidgetFactory.create_counter_widget()` at line 762 of widget_factory.py.

---

##### Bar Chart Widget (Benefit Type Claims)

```json
{
  "name": "benefit_type_claims",
  "queries": [{
    "name": "main_query",
    "query": {
      "datasetName": "claims_overview",
      "fields": [
        {"name": "benefit_type_group", "expression": "`benefit_type_group`"},
        {"name": "measure(total_claims)", "expression": "MEASURE(`total_claims`)"},
        {"name": "benefit_creation_date_quarter", "expression": "`benefit_creation_date_quarter`"}
      ],
      "disaggregated": false
    }
  }],
  "spec": {
    "version": 3,
    "widgetType": "bar",
    "mark": {"layout": "stack"},
    "encodings": {
      "x": {"fieldName": "measure(total_claims)", "scale": {"type": "quantitative"}},
      "y": {"fieldName": "benefit_creation_date_quarter", "scale": {"type": "categorical"}},
      "color": {"fieldName": "benefit_type_group", "scale": {"type": "categorical"}}
    },
    "data": {"queryName": "main_query"}
  }
}
```

**What each piece means:**
- `spec.version: 3` → bar charts must use version 3 (factory rule)
- `mark.layout: "stack"` → bars are stacked (not side by side)
- `encodings.x` → the horizontal axis shows the measure (claim count)
- `encodings.y` → the vertical axis shows quarters
- `encodings.color` → different colors for each benefit type
- `scale.type` → tells Databricks how to render the axis (number vs category)

**Factory code:** `WidgetFactory.create_bar_widget()` at line 327 of widget_factory.py.

---

##### Table Widget (Closed Claims Table)

```json
{
  "name": "closed_claims_table",
  "queries": [{
    "name": "main_query",
    "query": {
      "datasetName": "claims_overview",
      "fields": [
        {"name": "claim_casenumber", "expression": "`claim_casenumber`"},
        {"name": "benefit_type_group", "expression": "`benefit_type_group`"},
        {"name": "diagnosis_category", "expression": "`diagnosis_category`"},
        {"name": "termination_reason", "expression": "`termination_reason`"},
        {"name": "business_days_duration", "expression": "`business_days_duration`"}
      ],
      "filters": [{"expression": "`benefit_status` IN ('Closed')"}],
      "disaggregated": true,
      "orders": [{"direction": "DESC", "expression": "`business_days_duration`"}]
    }
  }],
  "spec": {
    "version": 2,
    "widgetType": "table",
    "rowsPerPage": 10,
    "encodings": {
      "columns": [
        {"fieldName": "claim_casenumber"},
        {"fieldName": "benefit_type_group"},
        {"fieldName": "diagnosis_category"},
        {"fieldName": "termination_reason"},
        {"fieldName": "business_days_duration"}
      ],
      "rowOrder": [{"by": "column-reversed", "field": {"index": 4}}]
    }
  }
}
```

**What each piece means:**
- `disaggregated: true` → show individual rows (not grouped/aggregated)
- `filters` → only show rows where Benefit Status = 'Closed'
- `orders` → sort by business_days_duration descending (longest first)
- `encodings.columns` → which columns to display
- `rowOrder` → sort the table by column index 4 (business_days_duration) in reverse

**Factory code:** `WidgetFactory.create_table_widget()` at line 619 of widget_factory.py.

---

##### Filter Widget (Diagnosis Category Filter)

```json
{
  "name": "filter_diagnosis",
  "queries": [{
    "name": "main_query",
    "query": {
      "datasetName": "claims_overview",
      "fields": [{"name": "diagnosis_category", "expression": "`diagnosis_category`"}],
      "disaggregated": false
    }
  }],
  "spec": {
    "version": 2,
    "widgetType": "filter-single-select",
    "frame": {"title": "Diagnosis Category", "showTitle": true},
    "encodings": {
      "fields": [{"fieldName": "diagnosis_category", "queryName": "main_query"}]
    }
  }
}
```

**What it does:** Creates a dropdown filter that controls all other widgets on the page. When you select a diagnosis category, all charts filter to show only that category.

**Factory code:** `WidgetFactory.create_filter_widget()` at line 795 of widget_factory.py.

---

#### Step 5: Assemble the Final JSON

The engine combines everything:

```json
{
  "datasets": [ ... all datasets ... ],
  "pages": [
    {
      "name": "page_id",
      "displayName": "Insurance Claims Overview",
      "layout": [
        { "widget": { ... counter ... }, "position": { "x": 0, "y": 0, "width": 4, "height": 2 } },
        { "widget": { ... counter ... }, "position": { "x": 4, "y": 0, "width": 4, "height": 2 } },
        { "widget": { ... bar chart ... }, "position": { "x": 0, "y": 2, "width": 8, "height": 6 } },
        ...
      ],
      "pageType": "PAGE_TYPE_CANVAS",
      "layoutVersion": "GRID_V1"
    }
  ]
}
```

**Code:** The `to_dict()` method on `LakeviewDashboard` (line 179 of [lakeview_model.py](file:///c:/Users/madhu/Desktop/db-tb/src/app/models/lakeview_model.py#L179-L190)) serializes the entire model to a Python dictionary, then `json.dumps()` converts it to the final JSON string.

---

### Version Rules (Enforced by WidgetFactory)

The factory **rejects** any widget with the wrong version number:

| Widget Type | Must Use Version | Why |
|-------------|-----------------|-----|
| Bar, Line, Area, Scatter, Pie, Heatmap | **3** | Chart rendering engine requires v3 |
| Counter (KPI) | **2** | Single-value display engine uses v2 |
| Filters (dropdown, date picker) | **2** | Filter engine uses v2 |
| Table | **1** | Table rendering engine uses v1 |
| Pivot | **3** | Pivot engine uses v3 |
| Combo (dual axis) | **1** | Combo engine uses v1 |

If you accidentally set version 2 on a bar chart, the factory throws an error and refuses to create it. This prevents invalid dashboards from being generated.

---

### What Happens When Something Can't Be Converted

The engine has a **fallback cascade**:

```
Chart needs x AND y axis but only has one field?
    → Check: Is it just one number? → Make it a KPI counter
    → Check: Does it have any fields? → Make it a table
    → No fields at all? → Skip it (log a warning)

Map chart?
    → Not supported in Lakeview → Convert to a table showing the data

Pie chart missing category or value?
    → Skip it (log a warning)
```

**Code:** Lines 236–298 of lakeview_generator.py handle all these fallback decisions.

---

## Summary: The Complete Journey

```
📊 Tableau Workbook
   │
   ├─ Calculated Field: "IF [Status]='Approved' THEN 'Yes' ELSE 'No' END"
   │    ↓ expression_compiler.py
   │    CASE WHEN `Status`='Approved' THEN 'Yes' ELSE 'No' END
   │
   ├─ Worksheet: "Benefit Type Claims" (bar chart)
   │    ↓ mark_type_resolver.py → "Bar Chart"
   │    ↓ tom_to_ubim.py → IntermediateWidget(BAR, x=quarter, y=claims, color=type)
   │    ↓ lakeview_generator.py → WidgetFactory.create_bar_widget()
   │    ↓ widget_factory.py → spec {version:3, widgetType:"bar", encodings:{x,y,color}}
   │
   ├─ Worksheet: "Total Claims" (single number)
   │    ↓ mark_type_resolver.py → "Text Table / KPI"
   │    ↓ lakeview_generator.py → detects single-measure → counter
   │    ↓ widget_factory.py → spec {version:2, widgetType:"counter", encodings:{value}}
   │
   └─ Dashboard Layout
        ↓ layout_engine.py → positions on grid
        ↓ lakeview_generator.py → assembles pages + datasets + widgets
        ↓ lakeview_model.py → to_dict() → json.dumps()
        ↓
   📄 Final Lakeview JSON (like Claims Overview.lvdash.json)
        ↓ api_client.py → POST to Databricks API
        ↓
   🖥️ Live Databricks Dashboard
```
