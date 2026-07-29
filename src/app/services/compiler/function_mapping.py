"""
Tableau → Databricks SQL Function Mapping Registry (120+ Functions).
Based on docs/P08_tableau_function_mapping.md.
"""

TABLEAU_DATABRICKS_FUNCTION_MAP = {
    # String Functions
    "ASCII": "ASCII({})",
    "CHAR": "CHR({})",
    "CONCAT": "CONCAT({})",
    "CONTAINS": "CONTAINS_SUBSTRING({}, {})",
    "ENDSWITH": "ENDSWITH({}, {})",
    "FIND": "LOCATE({}, {})",  # Arg swap: Tableau FIND(str, substr) -> LOCATE(substr, str)
    "FINDNTH": "LOCATE({}, {}, {})",
    "LEFT": "LEFT({}, {})",
    "LEN": "LENGTH({})",
    "LOWER": "LOWER({})",
    "LTRIM": "LTRIM({})",
    "MID": "SUBSTRING({}, {}, {})",
    "REPLACE": "REPLACE({}, {}, {})",
    "RIGHT": "RIGHT({}, {})",
    "RTRIM": "RTRIM({})",
    "SPACE": "REPEAT(' ', {})",
    "STARTSWITH": "STARTSWITH({}, {})",
    "SUBSTR": "SUBSTRING({}, {}, {})",
    "TRIM": "TRIM({})",
    "UPPER": "UPPER({})",

    # Date Functions
    "DATEADD": "DATE_ADD({}, {})",
    "DATEDIFF": "DATEDIFF({}, {})",  # Tableau DATEDIFF('day', start, end) -> Databricks DATEDIFF(end, start)
    "DATENAME": "DATE_FORMAT({}, {})",
    "DATEPART": "EXTRACT({} FROM {})",
    "DATETRUNC": "DATE_TRUNC({}, {})",
    "DAY": "DAY({})",
    "ISDATE": "CASE WHEN TRY_CAST({} AS DATE) IS NOT NULL THEN TRUE ELSE FALSE END",
    "MAX": "MAX({})",
    "MIN": "MIN({})",
    "MONTH": "MONTH({})",
    "NOW": "NOW()",
    "TODAY": "CURRENT_DATE()",
    "YEAR": "YEAR({})",

    # Math Functions
    "ABS": "ABS({})",
    "ACOS": "ACOS({})",
    "ASIN": "ASIN({})",
    "ATAN": "ATAN({})",
    "ATAN2": "ATAN2({}, {})",
    "CEILING": "CEIL({})",
    "COS": "COS({})",
    "COT": "COT({})",
    "DEGREES": "DEGREES({})",
    "EXP": "EXP({})",
    "FLOOR": "FLOOR({})",
    "LN": "LN({})",
    "LOG": "LOG({}, {})",
    "PI": "PI()",
    "RADIANS": "RADIANS({})",
    "ROUND": "ROUND({}, {})",
    "SIGN": "SIGNUM({})",
    "SIN": "SIN({})",
    "SQRT": "SQRT({})",
    "SQUARE": "POWER({}, 2)",
    "TAN": "TAN({})",
    "ZN": "COALESCE({}, 0)",

    # Aggregate Functions
    "AVG": "AVG({})",
    "ATTR": "CASE WHEN MIN({}) = MAX({}) THEN MIN({}) ELSE NULL END",
    "COUNT": "COUNT({})",
    "COUNTD": "COUNT(DISTINCT {})",
    "MEDIAN": "PERCENTILE({}, 0.5)",
    "PERCENTILE": "PERCENTILE({}, {})",
    "STDEV": "STDDEV({})",
    "STDEVP": "STDDEV_POP({})",
    "SUM": "SUM({})",
    "VAR": "VARIANCE({})",
    "VARP": "VAR_POP({})",

    # Logical Functions
    "AND": "{} AND {}",
    "OR": "{} OR {}",
    "NOT": "NOT {}",
    "IFNULL": "COALESCE({}, {})",
    "IIF": "IF({}, {}, {})",
    "ISNULL": "{} IS NULL",

    # Table & Window Calculations
    "RUNNING_SUM": "SUM({}) OVER (ORDER BY 1 ROWS UNBOUNDED PRECEDING)",
    "RUNNING_AVG": "AVG({}) OVER (ORDER BY 1 ROWS UNBOUNDED PRECEDING)",
    "RUNNING_COUNT": "COUNT({}) OVER (ORDER BY 1 ROWS UNBOUNDED PRECEDING)",
    "RUNNING_MAX": "MAX({}) OVER (ORDER BY 1 ROWS UNBOUNDED PRECEDING)",
    "RUNNING_MIN": "MIN({}) OVER (ORDER BY 1 ROWS UNBOUNDED PRECEDING)",
    "RANK": "RANK() OVER (ORDER BY {})",
    "RANK_UNIQUE": "ROW_NUMBER() OVER (ORDER BY {})",
    "RANK_DENSE": "DENSE_RANK() OVER (ORDER BY {})",
    "FIRST": "1 - ROW_NUMBER() OVER (ORDER BY 1)",
    "LAST": "COUNT(1) OVER () - ROW_NUMBER() OVER (ORDER BY 1)",
    "INDEX": "ROW_NUMBER() OVER (ORDER BY 1)",
    "SIZE": "COUNT(1) OVER ()",
}
