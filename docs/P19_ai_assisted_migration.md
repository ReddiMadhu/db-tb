# Phase 15: AI-Assisted Migration Strategy

This document outlines the architecture, boundaries, and implementation details for integrating Large Language Models (LLMs) into the Tableau to Databricks Lakeview migration pipeline.

## 1. Rule-Based vs LLM Boundary

The migration process prioritizes deterministic, rule-based compilation for speed, reliability, and cost. LLMs are leveraged exclusively as a fallback mechanism for complex, ambiguous, or loosely structured components where strict parsing fails or where semantic understanding is required.

| Task | Approach | Why |
|---|---|---|
| Simple function mapping (`LEFT` → `LEFT`) | Rules | 1:1 mapping, no ambiguity. Faster and 100% reliable. |
| Basic chart type mapping (`bar` → `bar`) | Rules | Direct mapping supported by both platforms. |
| Metadata Extraction | Rules | XML parsing is well-understood and structured. |
| Standard SQL generation | Rules | Abstract Syntax Trees (ASTs) map deterministically. |
| LOD expression translation (complex nested) | LLM-assisted | Context-dependent, multiple valid SQL translations, highly variable syntax. |
| Custom SQL with vendor-specific syntax | LLM-assisted | Requires semantic rewriting of proprietary functions to Databricks SQL. |
| Unsupported visualization suggestion | LLM | Requires understanding the user's intent to suggest the best alternative. |
| Naming normalization | LLM | Semantic understanding needed to convert technical names (`TX_AMT_YTD`) to display names (`Year-to-Date Transaction Amount`). |
| Documentation generation | LLM | Natural language generation for user-facing artifacts. |
| Error explanation | LLM | Converting stack traces into user-friendly migration guidance. |

## 2. LLM Integration Points

The integration of LLMs occurs at specific interception points in the migration pipeline:

1. **Expression Translation Fallback**:
   - **Trigger**: When the AST compiler encounters an unmapped Tableau function or nested LOD expression that exceeds heuristic complexity limits.
   - **Action**: Package the expression and table schema context and request a Databricks SQL equivalent.

2. **SQL Rewrite**:
   - **Trigger**: Custom SQL blocks containing recognized non-Databricks dialects (e.g., T-SQL `DATEADD`, Oracle `NVL`).
   - **Action**: Rewrite the entire query to Databricks SQL, maintaining identical output schema and semantic behavior.

3. **Visualization Recommendation**:
   - **Trigger**: Encounters of visualization types not natively supported in Lakeview (e.g., packed bubbles, bullet graphs).
   - **Action**: Provide the LLM with the measures and dimensions used, asking for the closest matching Lakeview visualization type and the rationale.

4. **Naming Conventions**:
   - **Trigger**: Post-processing step on generated datasets.
   - **Action**: Batch rename technical field names to clean, semantic display names.

5. **Migration Report Generation**:
   - **Trigger**: End of the migration pipeline.
   - **Action**: Summarize the migration logs into a human-readable summary of successes, partial migrations, and required manual actions.

6. **Error Recovery**:
   - **Trigger**: Validation failure of the generated Lakeview JSON.
   - **Action**: Feed the JSON and the JSON Schema error to the LLM to suggest or apply a structural fix.

7. **Schema Mapping**:
   - **Trigger**: Missing Unity Catalog mappings for source databases.
   - **Action**: Suggest Unity Catalog three-level namespaces (`catalog.schema.table`) based on semantic similarity to the Tableau data source names.

## 3. LLM Prompt Templates

Below are the standardized prompt templates used by the migration engine. These are populated at runtime using Jinja2 or standard Python string formatting.

### 3.1 Expression Translation Prompt

```json
{
  "system": "You are a Databricks SQL expert. Translate Tableau calculation expressions into valid Databricks SQL. Respond ONLY with the valid SQL expression, no markdown, no explanations.",
  "user": "Given the table schema: {{ schema_context }}\nTranslate this Tableau expression: `{{ tableau_expression }}`"
}
```
*Example input:* `IF [Sales] > 1000 THEN 'High' ELSE 'Low' END`
*Expected output:* `CASE WHEN Sales > 1000 THEN 'High' ELSE 'Low' END`

### 3.2 SQL Rewrite Prompt

```json
{
  "system": "You are a database migration specialist converting legacy custom SQL to Databricks SQL. Ensure all functions are Databricks-compatible. Preserve column aliases exactly. Output only the rewritten SQL statement.",
  "user": "Rewrite the following {{ source_dialect }} query to Databricks SQL:\n\n{{ legacy_sql }}"
}
```

### 3.3 Visualization Suggestion Prompt

```json
{
  "system": "You are an expert BI analyst. A user is migrating from Tableau to Databricks Lakeview. Lakeview supports: bar, line, scatter, pie, table, counter, combo, area, heat_map, histogram. Suggest the best alternative for an unsupported visualization.",
  "user": "The original visualization was a '{{ viz_type }}' using dimensions [{{ dimensions }}] and measures [{{ measures }}]. Which Lakeview visualization type should we use? Provide your response in JSON format with keys 'viz_type' and 'rationale'."
}
```

### 3.4 Error Explanation Prompt

```json
{
  "system": "You are a technical support assistant helping a user understand why their dashboard migration partially failed. Explain the error in simple terms and provide a manual workaround.",
  "user": "The migration failed for component '{{ component_name }}' with error: '{{ error_trace }}'. What does this mean and what should the user do in Databricks Lakeview to fix it?"
}
```

## 4. Guardrails and Validation

LLMs are non-deterministic; therefore, strict guardrails are enforced on all LLM outputs before integrating them into the final artifact.

1. **Syntax Validation**: Any SQL generated by the LLM (expressions or queries) is immediately parsed using `sqlglot` with the `databricks` dialect. If parsing fails, the output is discarded, and a fallback empty string or error placeholder is used.
2. **Schema Compliance**: Any JSON generated (e.g., for visualization modifications) is validated against the Lakeview JSON Schema.
3. **No Direct Execution**: The LLM output is used strictly to build the definition file (`.lvdash.json`). The migration tool *never* executes LLM-generated SQL against the user's data warehouse during the migration phase.
4. **Rate Limiting & Cost Management**:
   - Batch requests where possible.
   - Implement exponential backoff for API limits.
   - Set maximum token limits for input/output to prevent runaway costs on huge SQL blocks.
5. **Confidence Scoring & Audit Logging**:
   - If the LLM returns an unexpected format (e.g., markdown instead of raw SQL), the parser rejects it, logging a low-confidence failure.
   - Every LLM interaction is logged in `migration_audit.json` including the prompt, response, and validation result.

## 5. Model Selection

The choice of model depends on the complexity of the task and data privacy requirements.

| Task Category | Recommended Model | Rationale |
|---|---|---|
| Complex Reasoning (LOD, SQL Rewrite) | **GPT-4o** / **Claude 3.5 Sonnet** | High capability in cross-dialect SQL translation and understanding complex logical structures. |
| Simple Tasks (Naming, Formatting) | **GPT-4o-mini** / **Claude 3 Haiku** | Fast, inexpensive, and perfectly capable of semantic text manipulation. |
| Sensitive Environments (PII in SQL) | **Llama-3 (8B/70B)** (Self-hosted) | Ensures no data leaves the corporate boundary if custom SQL contains sensitive literal values. |

## 6. Implementation Architecture (Mermaid)

```mermaid
flowchart TD
    A[AST Compiler] --> B{Is Mapped?}
    B -- Yes --> C[Apply Rule]
    B -- No --> D[Package Context]
    D --> E[LLM Gateway API]
    E --> F[Generate Response]
    F --> G[Validation Layer (sqlglot)]
    G -- Valid --> H[Inject to AST]
    G -- Invalid --> I[Fallback to Comment/Error Node]
```
