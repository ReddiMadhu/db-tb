# PHASE 4 — EXPRESSION TRANSLATION ENGINE

## 1. Introduction
This document details the exhaustive implementation-level technical plan for the Expression Translation Engine, specifically focusing on the mapping of Tableau functions to their Databricks SQL equivalents. It serves as a canonical reference for migrating calculated fields, LOD expressions, and table calculations from Tableau to Databricks.

## 2. Complete Function Mapping

### 2.1 String Functions

| Tableau Function | Tableau Example | Databricks SQL Equivalent | Mapping Type | Edge Cases & Limitations |
| :--- | :--- | :--- | :--- | :--- |
| ASCII | `ASCII('A')` | `ascii('A')` | Direct | Returns first character's ASCII. Null if empty. |
| CHAR | `CHAR(65)` | `chr(65)` | Direct | Invalid ASCII codes return NULL in DB. |
| CONTAINS | `CONTAINS('abc', 'b')` | `contains('abc', 'b')` | Direct | Case sensitive in DB, Tableau might depend on collation. |
| ENDSWITH | `ENDSWITH('abc', 'c')` | `endswith('abc', 'c')` | Direct | Case sensitivity rules apply. |
| FIND | `FIND('abc', 'b')` | `locate('b', 'abc')` | Transformed | Argument order is reversed. |
| FINDNTH | `FINDNTH('a-b-c', '-', 2)` | `instr(regexp_extract('a-b-c', '^(?:[^-]*-){1}([^ -]*)-', 0), '-')` (complex regex) or UDF | Unsupported | Databricks lacks native FINDNTH. Requires UDF or complex regex. |
| LEFT | `LEFT('abc', 2)` | `left('abc', 2)` | Direct | Negative lengths handle differently. |
| LEN | `LEN('abc')` | `length('abc')` | Direct | DB counts characters, not bytes. |
| LOWER | `LOWER('ABC')` | `lower('ABC')` | Direct | Locale-specific lowercasing might differ. |
| LTRIM | `LTRIM(' abc')` | `ltrim(' abc')` | Direct | DB trims standard whitespace by default. |
| MAX | `MAX('a', 'b')` | `greatest('a', 'b')` | Transformed | Tableau MAX for strings is scalar MAX, DB uses GREATEST. |
| MID | `MID('abc', 2, 1)` | `substring('abc', 2, 1)` | Transformed | DB substring is 1-indexed. |
| MIN | `MIN('a', 'b')` | `least('a', 'b')` | Transformed | Tableau MIN for strings is scalar MIN, DB uses LEAST. |
| REPLACE | `REPLACE('abc', 'b', 'd')`| `replace('abc', 'b', 'd')` | Direct | Exact match replacement. |
| RIGHT | `RIGHT('abc', 2)` | `right('abc', 2)` | Direct | Negative length handling. |
| RTRIM | `RTRIM('abc ')` | `rtrim('abc ')` | Direct | Trims trailing spaces. |
| SPACE | `SPACE(3)` | `repeat(' ', 3)` | Transformed | DB has no SPACE, use repeat. |
| SPLIT | `SPLIT('a-b-c', '-', 2)` | `split('a-b-c', '-')[1]` | Transformed | DB array is 0-indexed, Tableau token index is 1-based (or negative for reverse). |
| STARTSWITH| `STARTSWITH('abc', 'a')` | `startswith('abc', 'a')` | Direct | Case sensitivity applies. |
| TRIM | `TRIM(' abc ')` | `trim(' abc ')` | Direct | DB trims both sides. |
| UPPER | `UPPER('abc')` | `upper('abc')` | Direct | Locale specific capitalization. |

### 2.2 Date Functions

| Tableau Function | Tableau Example | Databricks SQL Equivalent | Mapping Type | Edge Cases & Limitations |
| :--- | :--- | :--- | :--- | :--- |
| DATEADD | `DATEADD('month', 3, #2004-04-15#)` | `date_add(#date#, 3) ` or `add_months` or `date + INTERVAL 3 MONTH` | Transformed | DB uses INTERVAL syntax or specific functions like `add_months`. |
| DATEDIFF | `DATEDIFF('day', #date1#, #date2#)`| `datediff(#date2#, #date1#)` | Transformed | DB datediff only returns days. For other parts, complex math or `months_between` is needed. |
| DATENAME | `DATENAME('month', #date#)` | `date_format(#date#, 'MMMM')` | Transformed | Requires mapping Tableau date parts to Java date formats. |
| DATEPARSE| `DATEPARSE('dd.MM.yyyy', '15.04.2004')`| `to_date('15.04.2004', 'dd.MM.yyyy')` | Transformed | Format strings must be aligned (ICU vs Java SimpleDateFormat). |
| DATEPART | `DATEPART('year', #date#)` | `year(#date#)` or `extract(year from #date#)`| Transformed | Extract part mapping. |
| DATETRUNC| `DATETRUNC('month', #date#)` | `trunc(#date#, 'MM')` or `date_trunc('month', #date#)`| Transformed | DB `trunc` or `date_trunc`. |
| DAY | `DAY(#date#)` | `day(#date#)` | Direct | None. |
| ISDATE | `ISDATE('2004-04-15')` | `try_cast('2004-04-15' as date) is not null`| Transformed | DB lacks ISDATE natively. |
| MAKEDATE | `MAKEDATE(2004, 4, 15)` | `make_date(2004, 4, 15)` | Direct | Supported in newer DB runtimes. |
| MAKEDATETIME| `MAKEDATETIME(#date#, #time#)` | `cast(concat(cast(#date# as string), ' ', cast(#time# as string)) as timestamp)`| Transformed | DB doesn't have a direct combinator. |
| MAKETIME | `MAKETIME(14, 30, 0)` | `string(format_string('%02d:%02d:%02d', 14, 30, 0))`| Transformed | DB lacks TIME type natively, often represented as string or timestamp. |
| MONTH | `MONTH(#date#)` | `month(#date#)` | Direct | None. |
| NOW | `NOW()` | `current_timestamp()` | Direct | Timezone aware. |
| QUARTER | `QUARTER(#date#)` | `quarter(#date#)` | Direct | None. |
| TODAY | `TODAY()` | `current_date()` | Direct | None. |
| WEEK | `WEEK(#date#)` | `weekofyear(#date#)` | Transformed | ISO weeks vs standard weeks. |
| YEAR | `YEAR(#date#)` | `year(#date#)` | Direct | None. |
| ISOQUARTER| `ISOQUARTER(#date#)` | Math using ISOYEAR and ISOWEEK | Unsupported | Requires complex UDF/expression. |
| ISOWEEK | `ISOWEEK(#date#)` | `weekofyear(#date#)` | Transformed | DB `weekofyear` is ISO 8601. |
| ISOYEAR | `ISOYEAR(#date#)` | `year(#date# + interval ...)` | Transformed | Can use `extract(isoyear from #date#)` in newer DB runtimes. |

### 2.3 Number Functions

| Tableau Function | Tableau Example | Databricks SQL Equivalent | Mapping Type | Edge Cases & Limitations |
| :--- | :--- | :--- | :--- | :--- |
| ABS | `ABS(-7)` | `abs(-7)` | Direct | None. |
| ACOS | `ACOS(0.5)` | `acos(0.5)` | Direct | Returns radians. |
| ASIN | `ASIN(0.5)` | `asin(0.5)` | Direct | Returns radians. |
| ATAN | `ATAN(0.5)` | `atan(0.5)` | Direct | Returns radians. |
| ATAN2 | `ATAN2(y, x)` | `atan2(y, x)` | Direct | Parameter order matches DB. |
| CEILING | `CEILING(3.1)` | `ceil(3.1)` | Direct | Returns long. |
| COS | `COS(PI())` | `cos(pi())` | Direct | Radians input. |
| COT | `COT(PI()/4)` | `cot(pi()/4)` | Direct | Radians input. |
| DEGREES | `DEGREES(PI())` | `degrees(pi())` | Direct | Radians to degrees. |
| DIV | `DIV(11, 2)` | `div(11, 2)` or `11 div 2` | Direct | Integer division. |
| EXP | `EXP(2)` | `exp(2)` | Direct | e^x. |
| FLOOR | `FLOOR(3.9)` | `floor(3.9)` | Direct | Returns long. |
| HEXBINX | `HEXBINX(x, y)` | Complex UDF | Unsupported | DB lacks spatial hexbinning natively. |
| HEXBINY | `HEXBINY(x, y)` | Complex UDF | Unsupported | DB lacks spatial hexbinning natively. |
| LN | `LN(10)` | `ln(10)` | Direct | Natural log. |
| LOG | `LOG(10, 100)` | `log(10, 100)` | Direct | Base, value. |
| MAX | `MAX(a, b)` | `greatest(a, b)` | Transformed | Scalar max. |
| MIN | `MIN(a, b)` | `least(a, b)` | Transformed | Scalar min. |
| PI | `PI()` | `pi()` | Direct | None. |
| POWER | `POWER(2, 3)` | `power(2, 3)` or `pow(2, 3)` | Direct | None. |
| RADIANS | `RADIANS(180)` | `radians(180)` | Direct | Degrees to radians. |
| ROUND | `ROUND(3.1415, 2)`| `round(3.1415, 2)` | Direct | Round half to even vs round half up. |
| SIGN | `SIGN(-10)` | `signum(-10)` | Transformed | DB uses signum. |
| SIN | `SIN(PI()/2)` | `sin(pi()/2)` | Direct | Radians input. |
| SQRT | `SQRT(25)` | `sqrt(25)` | Direct | None. |
| SQUARE | `SQUARE(5)` | `pow(5, 2)` | Transformed | No native square. |
| TAN | `TAN(PI()/4)` | `tan(pi()/4)` | Direct | Radians input. |
| ZN | `ZN([Profit])` | `coalesce([Profit], 0)` | Transformed | Zero if null. |

### 2.4 Aggregate Functions

| Tableau Function | Tableau Example | Databricks SQL Equivalent | Mapping Type | Edge Cases & Limitations |
| :--- | :--- | :--- | :--- | :--- |
| ATTR | `ATTR([Cat])` | `if(min([Cat])=max([Cat]), min([Cat]), null)` | Transformed | ATTR returns * if multiple values exist, usually translated as NULL or custom string in DB. |
| AVG | `AVG([Sales])` | `avg([Sales])` | Direct | None. |
| COLLECT | `COLLECT([Geo])` | `collect_list` or `collect_set` | Transformed | Depends on usage context. |
| CORR | `CORR(X, Y)` | `corr(X, Y)` | Direct | None. |
| COUNT | `COUNT([ID])` | `count([ID])` | Direct | Ignores nulls. |
| COUNTD | `COUNTD([ID])` | `count(distinct [ID])` | Transformed | Exact distinct count. DB can use approx_count_distinct for speed. |
| COVAR | `COVAR(X, Y)` | `covar_samp(X, Y)` | Transformed | Sample covariance. |
| COVARP | `COVARP(X, Y)` | `covar_pop(X, Y)` | Transformed | Population covariance. |
| MAX | `MAX([Sales])` | `max([Sales])` | Direct | None. |
| MEDIAN | `MEDIAN([Sales])` | `percentile([Sales], 0.5)` | Transformed | Exact median. percentile_approx is faster. |
| MIN | `MIN([Sales])` | `min([Sales])` | Direct | None. |
| PERCENTILE | `PERCENTILE(X, 0.9)` | `percentile(X, 0.9)` | Direct | Exact percentile. |
| STDEV | `STDEV([Sales])` | `stddev_samp([Sales])` | Transformed | Sample stddev. |
| STDEVP | `STDEVP([Sales])` | `stddev_pop([Sales])` | Transformed | Population stddev. |
| SUM | `SUM([Sales])` | `sum([Sales])` | Direct | None. |
| VAR | `VAR([Sales])` | `var_samp([Sales])` | Transformed | Sample variance. |
| VARP | `VARP([Sales])` | `var_pop([Sales])` | Transformed | Population variance. |

### 2.5 Logical Functions

| Tableau Function | Tableau Example | Databricks SQL Equivalent | Mapping Type | Edge Cases & Limitations |
| :--- | :--- | :--- | :--- | :--- |
| AND | `A AND B` | `A AND B` | Direct | Standard ternary logic. |
| CASE | `CASE X WHEN Y THEN Z END`| `CASE X WHEN Y THEN Z END`| Direct | Identical syntax. |
| ELSE | `ELSE Z` | `ELSE Z` | Direct | Part of CASE/IF. |
| ELSEIF | `ELSEIF Y THEN Z` | `ELSEIF Y THEN Z` | Direct | Part of IF. |
| END | `END` | `END` | Direct | Terminates CASE/IF. |
| IF | `IF X THEN Y END` | `CASE WHEN X THEN Y END` | Transformed | DB doesn't have an IF statement in SELECT without IF() function. Translate to CASE WHEN. |
| IFNULL | `IFNULL(X, Y)` | `ifnull(X, Y)` or `coalesce(X, Y)` | Direct | Same behavior. |
| IIF | `IIF(X, Y, Z)` | `if(X, Y, Z)` | Transformed | DB uses `if` function. |
| IN | `X IN (Y, Z)` | `X IN (Y, Z)` | Direct | None. |
| ISNULL | `ISNULL(X)` | `X IS NULL` | Transformed | Syntax difference. |
| NOT | `NOT X` | `NOT X` | Direct | None. |
| OR | `X OR Y` | `X OR Y` | Direct | None. |
| SWITCH | N/A | N/A | Unsupported | Switch is part of CASE. |
| THEN | `THEN Y` | `THEN Y` | Direct | Part of CASE/IF. |
| WHEN | `WHEN X` | `WHEN X` | Direct | Part of CASE/IF. |
| ZN | `ZN(X)` | `coalesce(X, 0)` | Transformed | Handles numeric nulls. |

### 2.6 Type Conversion Functions

| Tableau Function | Tableau Example | Databricks SQL Equivalent | Mapping Type | Edge Cases & Limitations |
| :--- | :--- | :--- | :--- | :--- |
| DATE | `DATE('2004-04-15')`| `cast('2004-04-15' as date)` | Transformed | DB Cast. |
| DATETIME | `DATETIME('2004...')` | `cast('2004...' as timestamp)`| Transformed | DB Cast. |
| FLOAT | `FLOAT(3)` | `cast(3 as double)` | Transformed | DB uses double/float. |
| INT | `INT(3.14)` | `cast(3.14 as int)` | Transformed | Truncates decimal. |
| STR | `STR(3)` | `cast(3 as string)` | Transformed | Converts to string. |
| MAKEPOINT| `MAKEPOINT(lat, lon)` | `st_point(lon, lat)` | Transformed | Requires Photon/Mosaic or H3. DB st_point takes lon, lat (reversed from Tableau). |
| MAKELINE | `MAKELINE(p1, p2)` | `st_makeline(p1, p2)` | Transformed | Spatial extension needed. |

### 2.7 LOD Expressions
Level of Detail (LOD) expressions allow computing values at the data source level and the visualization level.

#### FIXED
*Tableau:* `{ FIXED [Region] : SUM([Sales]) }`
*Databricks:* `SUM(Sales) OVER (PARTITION BY Region)` or via JOINs.
*Rewrite Engine Strategy:*
For scalar projection, translate FIXED to window functions (`SUM(Sales) OVER (PARTITION BY Region)`).
For aggregation blocks, translate to Subqueries + JOINs:
```sql
SELECT main.*, lod.fixed_sales
FROM main_table main
LEFT JOIN (
    SELECT Region, SUM(Sales) as fixed_sales FROM main_table GROUP BY Region
) lod ON main.Region = lod.Region
```

#### INCLUDE
*Tableau:* `{ INCLUDE [Customer Name] : SUM([Sales]) }`
*Databricks:* This depends on the view level of detail. It computes the aggregate including the specified dimension, then aggregates again to the view level.
*Rewrite Engine Strategy:*
Requires knowing the View Dimensions (VD).
1. Inner query groups by `VD UNION [Customer Name]`.
2. Outer query groups by `VD`.
```sql
SELECT VD, AVG(inner_sales) FROM (
    SELECT VD, Customer_Name, SUM(Sales) as inner_sales
    FROM table GROUP BY VD, Customer_Name
) GROUP BY VD
```

#### EXCLUDE
*Tableau:* `{ EXCLUDE [Region] : SUM([Sales]) }`
*Databricks:* Compute aggregate removing the dimension from the view level.
*Rewrite Engine Strategy:*
1. Group by `VD MINUS [Region]`.
```sql
SUM(Sales) OVER (PARTITION BY (VD - Region))
```

### 2.8 Table Calculation Functions
Table calculations require Databricks Window functions. The specific `ORDER BY` and `PARTITION BY` depend on the addressing and partitioning fields defined in the Tableau view.

*Assumed Window: `OVER (PARTITION BY [PartitionFields] ORDER BY [AddressingFields])`*

| Tableau Function | Databricks SQL Equivalent | Notes |
| :--- | :--- | :--- |
| FIRST | `row_number() OVER (...) * -1 + 1` | FIRST() in Tableau returns 0 for first row, -1 for second, etc. DB `row_number()` is 1-based. |
| INDEX | `row_number() OVER (...)` | 1-based index. |
| LAST | `count(*) OVER (...) - row_number() OVER (...)` | Number of rows from current to end. |
| LOOKUP | `lag(expr, offset) OVER (...)` or `lead(expr, offset)`| If offset < 0 use lag, if > 0 use lead. |
| MODEL_* | N/A | Predictive functions unsupported in pure DB SQL. Needs MLflow UDF. |
| PREVIOUS_VALUE| Requires recursive CTEs. | Extremely complex to translate natively to SQL because it self-references. |
| RANK | `rank() OVER (...)` | Standard rank. |
| RANK_DENSE | `dense_rank() OVER (...)` | Dense rank. |
| RANK_MODIFIED | `count(*) OVER (PARTITION BY value) + rank() - 1` | Complex rewrite. |
| RANK_PERCENTILE| `percent_rank() OVER (...)` | Percentile rank. |
| RANK_UNIQUE | `row_number() OVER (...)` | Unique rank. |
| RUNNING_AVG | `avg(expr) OVER (PARTITION BY ... ORDER BY ... ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` | |
| RUNNING_COUNT | `count(expr) OVER (... ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` | |
| RUNNING_MAX | `max(expr) OVER (... ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` | |
| RUNNING_MIN | `min(expr) OVER (... ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` | |
| RUNNING_SUM | `sum(expr) OVER (... ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` | |
| SCRIPT_* | N/A | R/Python scripts unsupported natively in SQL. |
| SIZE | `count(*) OVER (PARTITION BY ...)` | Total rows in partition. |
| TOTAL | `sum(expr) OVER (PARTITION BY ...)` | Grand total for partition. |
| WINDOW_AVG | `avg(expr) OVER (... ROWS BETWEEN start AND end)` | Moving average. |
| WINDOW_MAX | `max(expr) OVER (... ROWS BETWEEN start AND end)` | Moving max. |
| WINDOW_MIN | `min(expr) OVER (... ROWS BETWEEN start AND end)` | Moving min. |
| WINDOW_SUM | `sum(expr) OVER (... ROWS BETWEEN start AND end)` | Moving sum. |

### 2.9 User Functions
These functions depend on the authenticated user context.

| Tableau Function | Databricks Equivalent | Notes |
| :--- | :--- | :--- |
| FULLNAME | `current_user()` | DB typically just returns the email/username. |
| ISMEMBEROF | `is_account_group_member(group)` | DB function. |
| ISUSERNAME | `current_user() = username` | Transformed. |
| USERDOMAIN | `split(current_user(), '@')[1]` | Extract domain from email. |
| USERNAME | `current_user()` | Direct mapping. |

### 2.10 Spatial Functions
Requires Databricks Mosaic or H3 extensions for full support.

| Tableau Function | Databricks Equivalent | Notes |
| :--- | :--- | :--- |
| AREA | `st_area(polygon)` | Requires spatial library. |
| BUFFER | `st_buffer(geom, dist)` | Requires spatial library. |
| DISTANCE | `st_distance(g1, g2)` | Requires spatial library. |
| INTERSECTION| `st_intersection(g1, g2)` | Requires spatial library. |
| LENGTH | `st_length(line)` | Requires spatial library. |


## 3. AST Parser Design for Tableau Expressions

To translate these functions programmatically, we implement an Abstract Syntax Tree (AST) parser for Tableau expressions.

### Lexer and Parser (ANTLR4)
We will define an ANTLR4 grammar (`TableauExpr.g4`) that understands Tableau's specific syntax:
- Square brackets for fields: `[Sales]`
- Braces for LOD expressions: `{ FIXED [Region] : SUM([Sales]) }`
- Case-insensitive function names.
- Date literals: `#2023-01-01#`

### AST Node Structure
```python
class ExprNode: pass
class FunctionCall(ExprNode):
    name: str
    args: List[ExprNode]
class FieldRef(ExprNode):
    name: str
class Literal(ExprNode):
    value: Any
    type: str
class LODExpr(ExprNode):
    level: str # FIXED, INCLUDE, EXCLUDE
    dimensions: List[FieldRef]
    aggregate: ExprNode
```

## 4. Visitor Pattern for Tree Traversal

The `TableauToSparkVisitor` extends the base AST visitor.

```python
class TableauToSparkVisitor:
    def visit_FunctionCall(self, node):
        func_name = node.name.upper()
        translated_args = [self.visit(arg) for arg in node.args]
        
        if func_name in SIMPLE_MAPPING:
            return f"{SIMPLE_MAPPING[func_name]}({', '.join(translated_args)})"
        elif func_name == 'IFNULL':
            return f"coalesce({translated_args[0]}, {translated_args[1]})"
        # Complex rewrites...
        
    def visit_FieldRef(self, node):
        return f"`{node.name}`" # Escaped for Databricks
        
    def visit_LODExpr(self, node):
        # Generates a Window function or flags for CTE generation
        dims = ", ".join(self.visit(d) for d in node.dimensions)
        agg = self.visit(node.aggregate)
        if node.level == 'FIXED':
            return f"{agg} OVER (PARTITION BY {dims})"
```

## 5. Rewrite Rule Engine Architecture

The rewrite engine runs multiple passes over the AST before emitting SQL:

1. **Type Inference Pass:** Determines the return type of each node to apply correct implicit casts (e.g., Integer division vs Float division).
2. **LOD Unrolling Pass:** If an LOD cannot be satisfied by a Window function (e.g., nested LODs), it extracts the LOD into a CTE and replaces the node with a reference to the CTE's output column.
3. **Table Calculation Context Pass:** Injects the current View's addressing and partitioning fields into Table Calculation nodes (e.g., expanding `RUNNING_SUM(expr)` to include the `OVER (...)` clause).

## 6. Expression Optimization Passes

Once the AST is translated to a Databricks SQL AST:
- **Constant Folding:** Evaluate expressions like `DATEADD('day', 1, #2023-01-01#)` at compile time.
- **Redundant Coalesce Removal:** `COALESCE(COALESCE(A, 0), 0)` -> `COALESCE(A, 0)`.
- **Window Function Deduplication:** If multiple expressions use the exact same `OVER` clause, ensure the generated SQL aliases them efficiently or relies on Catalyst optimizer.

## 7. Validation of Translated Expressions

To ensure semantic equivalence:
1. **Unit Testing Framework:** A suite of 500+ Tableau expressions and their expected DB SQL outputs.
2. **Dual Execution Engine:** During migration, run the Tableau expression (via Tableau Server or Extract) and the Databricks SQL on the same dataset. Compare outputs using a hash or direct row comparison.
3. **Edge Case Fuzzing:** Generate permutations of NULLs, negative numbers, and boundary dates to ensure Databricks functions (like `DATEDIFF`) behave exactly like Tableau's C++ data engine.
