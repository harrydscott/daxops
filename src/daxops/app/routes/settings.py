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


@router.get("/settings", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    """Return current settings."""
    return SettingsResponse(
        model_path=app_state.model_path,
        model_loaded=app_state.model is not None,
    )


@router.put("/settings/model-path", response_model=SettingsResponse)
def set_model_path(req: SetModelPathRequest) -> SettingsResponse:
    """Set the model path and trigger a scan."""
    path = req.model_path
    if not Path(path).exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {path}")
    app_state.set_model_path(path)
    app_state.scan()
    return SettingsResponse(
        model_path=app_state.model_path,
        model_loaded=app_state.model is not None,
    )


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
