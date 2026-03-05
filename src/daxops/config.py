"""Configuration file support for DaxOps (.daxops.yml)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ScoreThresholds(BaseModel):
    """Thresholds for scoring tiers."""
    bronze_min: int = 10
    silver_min: int = 10
    gold_min: int = 8


class CheckThresholds(BaseModel):
    """Thresholds for health check findings."""
    max_errors: int = 0
    max_warnings: int | None = None  # None = unlimited
    max_info: int | None = None


class DaxOpsConfig(BaseModel):
    """Root configuration model."""
    score: ScoreThresholds = Field(default_factory=ScoreThresholds)
    check: CheckThresholds = Field(default_factory=CheckThresholds)
    exclude_rules: list[str] = Field(default_factory=list)
    exclude_tables: list[str] = Field(default_factory=list)
    severity: str | None = None  # default severity filter


_DEFAULT_CONFIG = DaxOpsConfig()


def load_config(start_path: Path | None = None) -> DaxOpsConfig:
    """Load .daxops.yml by walking up from start_path (or cwd)."""
    search = start_path or Path.cwd()
    if search.is_file():
        search = search.parent

    for directory in [search, *search.parents]:
        for name in (".daxops.yml", ".daxops.yaml", "daxops.yml"):
            cfg_path = directory / name
            if cfg_path.is_file():
                return _parse_config(cfg_path)
    return _DEFAULT_CONFIG


def _parse_config(path: Path) -> DaxOpsConfig:
    """Parse a YAML config file into DaxOpsConfig."""
    try:
        import yaml
    except ImportError:
        # Fallback: try to parse simple YAML manually
        return _parse_simple_yaml(path)

    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return DaxOpsConfig(**data)


def _parse_simple_yaml(path: Path) -> DaxOpsConfig:
    """Minimal YAML parser for when PyYAML isn't installed."""
    import json as _json

    data: dict[str, Any] = {}
    current_section: str | None = None
    text = path.read_text()

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Top-level key (no indent)
        if not line[0].isspace() and ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()
            if value:
                data[key] = _coerce(value)
                current_section = None
            else:
                current_section = key
                data[key] = {}
        elif current_section and ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()
            if value:
                data[current_section][key] = _coerce(value)

    return DaxOpsConfig(**data)


def _coerce(value: str) -> Any:
    """Coerce a string value to int/bool/None/list/str."""
    if value.lower() == "null" or value == "~":
        return None
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    try:
        return int(value)
    except ValueError:
        pass
    # Simple list: [a, b, c]
    if value.startswith("[") and value.endswith("]"):
        items = value[1:-1].split(",")
        return [i.strip().strip("'\"") for i in items if i.strip()]
    return value.strip("'\"")
