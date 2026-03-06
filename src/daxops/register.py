"""External Tool registration for Power BI Desktop.

Creates/removes the DaxOps.pbitool.json file in the PBI External Tools folder
so DaxOps appears in the External Tools ribbon inside Power BI Desktop.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


PBITOOL_FILENAME = "DaxOps.pbitool.json"

# Minimal 16x16 orange/white "D" icon as base64 PNG
ICON_DATA = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAA"
    "WElEQVR42mNkYPj/n4EIwMjIyECUAUwMRAJGYgwgGjANI8kABnINA2lmIBswkGoA0YBx"
    "GEb8Z6AOIAcwUW4APdygkWoYepgZNFIN0JvwkWoY8fGALAAAOI0gEYGMR+sAAAAASUVO"
    "RK5CYII="
)


def get_external_tools_folder(override: str | None = None) -> Path:
    """Return the PBI Desktop External Tools folder path.

    Args:
        override: Explicit path override. If provided, use it directly.

    Returns:
        Path to the External Tools folder.

    Raises:
        FileNotFoundError: If the folder doesn't exist and can't be created.
    """
    if override:
        return Path(override)

    if sys.platform != "win32":
        raise OSError(
            "External Tool registration requires Windows (Power BI Desktop is Windows-only).\n"
            "On Mac/Linux, use 'daxops app --model-path <folder>' instead."
        )

    common_files = os.environ.get("CommonProgramFiles", "")
    if not common_files:
        common_files = r"C:\Program Files\Common Files"

    return Path(common_files) / "Microsoft Shared" / "Power BI Desktop" / "External Tools"


def build_pbitool_json() -> dict:
    """Build the .pbitool.json content for External Tool registration."""
    return {
        "version": "1.0",
        "name": "DaxOps",
        "description": "AI Readiness & Health Checks for Semantic Models",
        "path": sys.executable,
        "arguments": '-m daxops app --ssas-server "%server%" --database "%database%"',
        "iconData": ICON_DATA,
    }


def register_tool(path_override: str | None = None) -> Path:
    """Register DaxOps as a PBI Desktop External Tool.

    Returns:
        Path to the created .pbitool.json file.
    """
    folder = get_external_tools_folder(path_override)
    folder.mkdir(parents=True, exist_ok=True)

    target = folder / PBITOOL_FILENAME
    content = build_pbitool_json()
    target.write_text(json.dumps(content, indent=2), encoding="utf-8")
    return target


def unregister_tool(path_override: str | None = None) -> Path | None:
    """Remove DaxOps from PBI Desktop External Tools.

    Returns:
        Path of the removed file, or None if it didn't exist.
    """
    folder = get_external_tools_folder(path_override)
    target = folder / PBITOOL_FILENAME
    if target.exists():
        target.unlink()
        return target
    return None
