import sys
import json
from pathlib import Path

sys.path.insert(0, "src")

from app.services.parser.tableau_extractor import parse_workbook
from app.services.normalizer.tom_to_ubim import normalize_tom_to_ubim
from app.services.generator.lakeview_generator import generate_lakeview_dashboard
from app.services.validator.validation_engine import validate_lakeview_dashboard

twb_path = r"uploads/33c429493082/Insurance Claim Dashboard.twbx"
tb_meta = parse_workbook(twb_path)
ubim = normalize_tom_to_ubim(tb_meta, default_catalog="main", default_schema="default")
lakeview = generate_lakeview_dashboard(ubim)

val_report = validate_lakeview_dashboard(lakeview)

lakeview_dict = lakeview.to_dict()

# Save updated json output
out_dir = Path("outputs/33c429493082")
out_dir.mkdir(parents=True, exist_ok=True)
with open(out_dir / "33c429493082.lvdash.json", "w", encoding="utf-8") as f:
    json.dump(lakeview_dict, f, indent=2)

with open(out_dir / "33c429493082_pretty.lvdash.json", "w", encoding="utf-8") as f:
    json.dump(lakeview_dict, f, indent=2)

print("=== 6-TIER VALIDATION SUITE RESULTS (WITH DEFAULT CATALOG/SCHEMA) ===")
print("Passed:", val_report.get("is_valid"))
print("Total Errors:", len(val_report.get("errors", [])))
print("Total Warnings:", len(val_report.get("warnings", [])))
print("\n--- ERRORS ---")
for err in val_report.get("errors", []):
    print(" [ERROR]", err)
print("\n--- WARNINGS ---")
for warn in val_report.get("warnings", []):
    print(" [WARN]", warn)
