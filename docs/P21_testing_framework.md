# Phase 17: Testing Framework

This document details the comprehensive testing strategy for the Tableau to Databricks Lakeview migration tool, ensuring high fidelity, reliability, and regression prevention.

## 1. Test Categories

1. **Unit Tests**: Test individual classes and functions (e.g., `TableauXMLParser`, `ASTCompiler`, `SQLGenerator`). Focus on deterministic I/O.
2. **Integration Tests**: Test the pipeline stages end-to-end (from `.twb` input to `.lvdash.json` output).
3. **Golden File Tests**: Snapshot testing. Compare the tool's output against a human-verified "golden" standard file.
4. **Schema Validation Tests**: Assert that every generated output JSON string perfectly validates against the official Lakeview JSON Schema.
5. **SQL Validation Tests**: Parse all generated SQL datasets using `sqlglot` to verify Databricks dialect compliance.
6. **API Integration Tests**: (Optional/Staging) Push the generated JSON to a real Databricks workspace via the API to verify the platform accepts it without internal errors.
7. **Visual Regression Tests**: (Manual/Semi-automated) Compare screenshots of the original Tableau dashboard and the rendered Lakeview dashboard.
8. **Performance Tests**: Benchmark the time taken to process large XML files and the memory footprint of the parser.
9. **Stress Tests**: Throw pathologically large or deeply nested workbooks (e.g., 100+ worksheets, 50+ data sources) at the tool.
10. **Failure Injection Tests**: Simulate corrupted XML, missing attributes, or LLM API timeouts to verify graceful error handling and reporting.

## 2. Golden File Test Framework

Golden files are the backbone of preventing regressions in the compiler logic.

- **Input**: A curated directory of sample `.twb` files representing various features (bar charts, parameters, LODs).
- **Expected Output**: A paired `.lvdash.json` reference file.
- **Comparison**: Tests generate a new JSON and perform a structural comparison against the golden JSON. UUIDs (which are randomly generated for Lakeview widgets) are stripped or ignored during comparison.

### Example Pytest implementation

```python
import pytest
import json
from pathlib import Path
from migration_tool.pipeline import run_migration

def strip_ids(obj):
    """Recursively remove volatile IDs for stable comparison."""
    if isinstance(obj, dict):
        return {k: strip_ids(v) for k, v in obj.items() if k not in ["id", "dataset_id"]}
    elif isinstance(obj, list):
        return [strip_ids(i) for i in obj]
    return obj

def test_golden_files(tmp_path):
    golden_dir = Path("tests/fixtures/golden")
    
    for twb_file in golden_dir.glob("*.twb"):
        expected_json_path = twb_file.with_suffix(".lvdash.json")
        
        # Run migration pipeline
        output_json_path = tmp_path / "output.json"
        run_migration(twb_file, output_json_path)
        
        with open(output_json_path) as f_out, open(expected_json_path) as f_expected:
            actual = json.load(f_out)
            expected = json.load(f_expected)
            
            # Compare structural equivalence, ignoring random IDs
            assert strip_ids(actual) == strip_ids(expected)
```

## 3. Test Data Generation

To ensure thorough coverage, synthetic Tableau workbooks are generated programmatically (or built manually as templates) covering:
- Every supported visualization type (Bar, Line, Scatter, etc.)
- Various filter configurations (Global, Local, Context)
- Complex nested calculations
- Multiple dashboards in a single workbook
- Edge cases: Empty dashboards, disconnected data sources, unmapped custom SQL.

## 4. CI/CD Test Pipeline

Testing is enforced via GitHub Actions on every pull request.

- **Matrix Testing**: Run across Python 3.9, 3.10, 3.11, and 3.12.
- **Code Coverage**: Enforced >80% coverage using `pytest-cov`.
- **Linting & Formatting**: `ruff` for fast linting/formatting, `mypy` for strict type checking.
- **Security Scanning**: `bandit` and `safety` to scan for vulnerable dependencies.

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.9", "3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install dependencies
        run: |
          pip install -r requirements-dev.txt
      - name: Lint and Type Check
        run: |
          ruff check .
          mypy src/
      - name: Run Pytest
        run: |
          pytest tests/ --cov=src --cov-report=xml
      - name: Upload Coverage
        uses: codecov/codecov-action@v3
```

## 5. Test Reporting

- **JUnit XML**: Pytest outputs results in JUnit format for integration with CI dashboards.
- **Migration Accuracy Metrics**: A custom script evaluates a large corpus of real-world workbooks and outputs an HTML report detailing the percentage of worksheets successfully migrated vs. those requiring manual intervention or LLM fallback.
- **Coverage Matrix**: A maintained markdown table tracking which Tableau features have corresponding unit and golden file tests.
