import os
import yaml
from typing import Dict, Any
from app.models.lakeview_model import LakeviewDashboard


def generate_databricks_asset_bundle(
    dashboard_name: str,
    lakeview_dash: LakeviewDashboard,
    output_dir: str
) -> Dict[str, str]:
    """
    Generates a Databricks Asset Bundle (DABs) databricks.yml configuration file
    and serialized dashboard JSON artifact for GitOps CI/CD pipelines.
    """
    os.makedirs(output_dir, exist_ok=True)
    json_filename = f"{dashboard_name.lower().replace(' ', '_')}.lvdash.json"
    json_filepath = os.path.join(output_dir, json_filename)
    lakeview_dash.save_to_file(json_filepath)

    bundle_config = {
        "bundle": {
            "name": dashboard_name.lower().replace(' ', '_')
        },
        "resources": {
            "dashboards": {
                f"{dashboard_name.lower().replace(' ', '_')}_dashboard": {
                    "display_name": dashboard_name,
                    "file_path": f"./{json_filename}",
                    "warehouse_id": "${var.warehouse_id}"
                }
            }
        },
        "targets": {
            "dev": {
                "mode": "development",
                "default": True,
                "workspace": {
                    "host": "${var.databricks_host}"
                }
            },
            "prod": {
                "mode": "production",
                "workspace": {
                    "host": "${var.databricks_host}"
                }
            }
        }
    }

    yaml_filepath = os.path.join(output_dir, "databricks.yml")
    with open(yaml_filepath, "w", encoding="utf-8") as f:
        yaml.dump(bundle_config, f, default_flow_style=False)

    return {
        "yaml_path": yaml_filepath,
        "json_path": json_filepath
    }
