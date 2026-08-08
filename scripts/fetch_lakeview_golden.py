#!/usr/bin/env python3
"""Developer utility: fetch a Databricks Lakeview dashboard JSON into demo_goldens/.

Edit the constants below, then run:

    python scripts/fetch_lakeview_golden.py
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ── Edit these values ────────────────────────────────────────────────────────
DATABRICKS_HOST = ""  # https://<workspace>.azuredatabricks.net
DASHBOARD_ID = ""
PAT_TOKEN = ""  # <personal-access-token>
OUTPUT_DIR = "demo_goldens"
OUTPUT_FILENAME = "Claims Overview.lvdash.json"
# ─────────────────────────────────────────────────────────────────────────────


def main() -> int:
    host = (DATABRICKS_HOST or "").strip().rstrip("/")
    dashboard_id = (DASHBOARD_ID or "").strip()
    token = (PAT_TOKEN or "").strip()
    output_dir = (OUTPUT_DIR or "demo_goldens").strip()
    output_filename = (OUTPUT_FILENAME or "").strip()

    if not host:
        print("Error: DATABRICKS_HOST is empty. Edit the constants at the top of this script.")
        return 1
    if not dashboard_id:
        print("Error: DASHBOARD_ID is empty. Edit the constants at the top of this script.")
        return 1
    if not token:
        print("Error: PAT_TOKEN is empty. Edit the constants at the top of this script.")
        return 1
    if not output_filename:
        print("Error: OUTPUT_FILENAME is empty. Edit the constants at the top of this script.")
        return 1

    url = f"{host}/api/2.0/lakeview/dashboards/{dashboard_id}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            payload = json.loads(body)
    except urllib.error.HTTPError as exc:
        err_body = ""
        try:
            err_body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        print(f"API request failed. HTTP status: {exc.code}")
        if err_body:
            print(err_body[:2000])
        return 1
    except urllib.error.URLError as exc:
        print(f"API request failed: {exc.reason}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"Failed to parse API response as JSON: {exc}")
        return 1

    serialized = payload.get("serialized_dashboard")
    if serialized is None:
        print("Error: response missing 'serialized_dashboard'.")
        print(f"Top-level keys: {sorted(payload.keys())}")
        return 1

    if isinstance(serialized, str):
        try:
            dashboard_obj = json.loads(serialized)
        except json.JSONDecodeError as exc:
            print(f"Failed to parse serialized_dashboard as JSON: {exc}")
            return 1
    elif isinstance(serialized, dict):
        dashboard_obj = serialized
    else:
        print(f"Error: unexpected serialized_dashboard type: {type(serialized).__name__}")
        return 1

    dashboard_name = (
        payload.get("display_name")
        or payload.get("name")
        or dashboard_obj.get("displayName")
        or output_filename
    )

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / output_filename
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(dashboard_obj, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print("Dashboard extracted successfully.")
    print()
    print(f"Dashboard ID: {dashboard_id}")
    print(f"Dashboard Name: {dashboard_name}")
    print("Output:")
    print(str(out_path).replace("\\", "/"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
