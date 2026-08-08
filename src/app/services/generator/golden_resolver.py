"""Resolve curated golden Lakeview JSON files for RFP demo overrides."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

# repo root: src/app/services/generator/golden_resolver.py → ../../../../
_REPO_ROOT = Path(__file__).resolve().parents[4]
_GOLDEN_DIR = _REPO_ROOT / "demo_goldens"


def golden_dir() -> Path:
    return _GOLDEN_DIR


def resolve_golden(source_filename: str) -> Optional[str]:
    """Return absolute path to golden file if it exists, else None.

    Matches: demo_goldens/{Path(source_filename).stem}.lvdash.json
    Exact stem match (spaces/casing preserved). No fuzzy matching.
    """
    if not source_filename:
        return None
    stem = Path(source_filename).stem
    if not stem:
        return None
    candidate = _GOLDEN_DIR / f"{stem}.lvdash.json"
    if candidate.is_file():
        return str(candidate.resolve())
    return None


def apply_golden_override(
    *,
    source_filename: str,
    generated_path: str,
    official_path: str,
) -> Tuple[bool, Optional[str]]:
    """Copy golden (or generated) bytes to official_path.

    Returns (golden_override, golden_source_relpath_or_None).
    """
    import shutil

    golden_abs = resolve_golden(source_filename)
    os.makedirs(os.path.dirname(official_path) or ".", exist_ok=True)

    if golden_abs:
        shutil.copyfile(golden_abs, official_path)
        rel = f"demo_goldens/{Path(source_filename).stem}.lvdash.json"
        return True, rel

    shutil.copyfile(generated_path, official_path)
    return False, None
