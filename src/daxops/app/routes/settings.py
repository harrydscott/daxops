"""GET/PUT /api/settings — model path and configuration."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from daxops.app.state import app_state

router = APIRouter()


class SettingsResponse(BaseModel):
    model_path: str | None
    model_loaded: bool
    exclude_rules: list[str]
    thresholds: dict[str, int]


class SetModelPathRequest(BaseModel):
    model_path: str


class DirectoryEntry(BaseModel):
    name: str
    path: str
    is_dir: bool
    is_model: bool


class BrowseResponse(BaseModel):
    current: str
    parent: str | None
    entries: list[DirectoryEntry]


def _settings_response() -> SettingsResponse:
    cfg = app_state.config
    return SettingsResponse(
        model_path=app_state.model_path,
        model_loaded=app_state.model is not None,
        exclude_rules=cfg.exclude_rules,
        thresholds={
            "bronze_min": cfg.score.bronze_min,
            "silver_min": cfg.score.silver_min,
            "gold_min": cfg.score.gold_min,
        },
    )


@router.get("/settings", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    """Return current settings."""
    return _settings_response()


@router.put("/settings/model-path", response_model=SettingsResponse)
def set_model_path(req: SetModelPathRequest) -> SettingsResponse:
    """Set the model path and trigger a scan."""
    path = req.model_path
    if not Path(path).exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {path}")
    app_state.set_model_path(path)
    app_state.scan()
    return _settings_response()


class RulesConfigRequest(BaseModel):
    exclude_rules: list[str]
    thresholds: dict[str, int]


@router.put("/settings/rules", response_model=SettingsResponse)
def set_rules_config(req: RulesConfigRequest) -> SettingsResponse:
    """Update rule exclusions and score thresholds."""
    app_state.config.exclude_rules = req.exclude_rules
    if "bronze_min" in req.thresholds:
        app_state.config.score.bronze_min = req.thresholds["bronze_min"]
    if "silver_min" in req.thresholds:
        app_state.config.score.silver_min = req.thresholds["silver_min"]
    if "gold_min" in req.thresholds:
        app_state.config.score.gold_min = req.thresholds["gold_min"]
    return _settings_response()


@router.get("/browse", response_model=BrowseResponse)
def browse_directory(path: str | None = None) -> BrowseResponse:
    """Browse the filesystem for model folders."""
    target = Path(path) if path else Path.home()
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {target}")

    entries = []
    try:
        for item in sorted(target.iterdir()):
            if item.name.startswith("."):
                continue
            is_dir = item.is_dir()
            is_model = False
            if is_dir:
                try:
                    is_model = (item / "model.tmdl").exists() or any(
                        f.suffix == ".pbip" for f in item.iterdir() if f.is_file()
                    )
                except (PermissionError, OSError):
                    pass
            entries.append(DirectoryEntry(
                name=item.name,
                path=str(item),
                is_dir=is_dir,
                is_model=is_model,
            ))
    except PermissionError:
        pass

    parent = str(target.parent) if target.parent != target else None
    return BrowseResponse(current=str(target), parent=parent, entries=entries)
