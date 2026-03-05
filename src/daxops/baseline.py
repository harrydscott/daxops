"""Baseline/suppress — save current findings, future runs show only new issues."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from daxops.health.rules import Finding

BASELINE_FILENAME = ".daxops-baseline.json"


def _finding_key(f: Finding) -> str:
    """Create a stable key for a finding (rule + object_path)."""
    return f"{f.rule}::{f.object_path}"


def save_baseline(findings: list[Finding], model_path: str | Path) -> Path:
    """Save current findings as a baseline file next to the model."""
    from daxops.parser.tmdl import resolve_model_root

    root = resolve_model_root(model_path)
    baseline_path = root / BASELINE_FILENAME

    data = {
        "version": 1,
        "findings": [
            {
                "key": _finding_key(f),
                "rule": f.rule,
                "severity": f.severity.value,
                "message": f.message,
                "object_path": f.object_path,
            }
            for f in findings
        ],
    }

    baseline_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return baseline_path


def load_baseline(model_path: str | Path) -> set[str]:
    """Load baseline finding keys from a baseline file."""
    from daxops.parser.tmdl import resolve_model_root

    root = resolve_model_root(model_path)
    baseline_path = root / BASELINE_FILENAME

    if not baseline_path.exists():
        return set()

    data = json.loads(baseline_path.read_text(encoding="utf-8"))
    return {f["key"] for f in data.get("findings", [])}


def filter_new_findings(findings: list[Finding], baseline_keys: set[str]) -> list[Finding]:
    """Return only findings not present in the baseline."""
    return [f for f in findings if _finding_key(f) not in baseline_keys]
