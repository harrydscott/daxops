"""Local SSAS connection for Power BI Desktop integration.

Connects to the Analysis Services instance that PBI Desktop spins up
on localhost when a .pbip project is open. Read-only — used for scanning
the live model state.

Requires pyadomd (Windows-only, optional dependency):
    pip install daxops[xmla]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from daxops.models.schema import SemanticModel
from daxops.xmla import build_model_from_metadata, _query_dmv, DMV_TABLES, DMV_COLUMNS, DMV_MEASURES, DMV_RELATIONSHIPS, DMV_PARTITIONS


def connect_ssas(server: str, database: str) -> Any:
    """Connect to a local SSAS instance via pyadomd.

    Args:
        server: Server address, e.g. 'localhost:12345'.
        database: Database/catalog name.

    Returns:
        An open pyadomd connection.

    Raises:
        ImportError: If pyadomd is not installed.
        ConnectionError: If the connection fails.
    """
    try:
        from pyadomd import Pyadomd  # type: ignore[import-untyped]
    except ImportError:
        raise ImportError(
            "SSAS connection requires pyadomd (Windows-only). Install with:\n"
            "  pip install daxops[xmla]\n\n"
            "On Mac/Linux, use --model-path to read from TMDL files instead."
        )

    conn_str = f"Provider=MSOLAP;Data Source={server};Catalog={database}"
    try:
        return Pyadomd(conn_str)
    except Exception as e:
        raise ConnectionError(
            f"Failed to connect to SSAS at {server} (database: {database}).\n"
            f"Is Power BI Desktop running with a model open?\n"
            f"Error: {e}"
        ) from e


def scan_ssas(server: str, database: str) -> SemanticModel:
    """Scan a local SSAS instance and return a SemanticModel.

    This connects to the Analysis Services instance spun up by PBI Desktop,
    queries DMV views, and converts to the same SemanticModel used throughout
    DaxOps.

    Args:
        server: Server address, e.g. 'localhost:12345'.
        database: Database/catalog name.

    Returns:
        A SemanticModel representing the live model.
    """
    conn = connect_ssas(server, database)
    try:
        raw_tables = _query_dmv(conn, DMV_TABLES)
        raw_columns = _query_dmv(conn, DMV_COLUMNS)
        raw_measures = _query_dmv(conn, DMV_MEASURES)
        raw_relationships = _query_dmv(conn, DMV_RELATIONSHIPS)
        raw_partitions = _query_dmv(conn, DMV_PARTITIONS)

        return build_model_from_metadata(
            database, raw_tables, raw_columns, raw_measures,
            raw_relationships, raw_partitions,
        )
    finally:
        conn.close()


def find_workspace_tmdl(server: str) -> Path | None:
    """Detect the TMDL project folder from the SSAS workspace directory.

    PBI Desktop stores workspace data in:
        %LOCALAPPDATA%\\Microsoft\\Power BI Desktop\\AnalysisServicesWorkspaces\\

    Each workspace folder contains a Data/ directory with msmdsrv.port.txt.
    We match the port from the server address to find the right workspace,
    then look for a .pbip project reference.

    Args:
        server: Server address like 'localhost:12345'.

    Returns:
        Path to the TMDL folder, or None if not found.
    """
    if sys.platform != "win32":
        return None

    # Extract port from server string
    port = _extract_port(server)
    if not port:
        return None

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if not local_app_data:
        return None

    workspaces_dir = Path(local_app_data) / "Microsoft" / "Power BI Desktop" / "AnalysisServicesWorkspaces"
    if not workspaces_dir.exists():
        return None

    # Search workspace directories for matching port
    for ws_dir in workspaces_dir.iterdir():
        if not ws_dir.is_dir():
            continue
        port_file = ws_dir / "Data" / "msmdsrv.port.txt"
        if port_file.exists():
            try:
                ws_port = port_file.read_text().strip()
                if ws_port == port:
                    return _find_project_from_workspace(ws_dir)
            except (OSError, ValueError):
                continue

    return None


def _extract_port(server: str) -> str | None:
    """Extract port number from a server string like 'localhost:12345'."""
    if ":" in server:
        parts = server.rsplit(":", 1)
        if parts[1].isdigit():
            return parts[1]
    return None


def _find_project_from_workspace(ws_dir: Path) -> Path | None:
    """Look for the source .pbip project path from a workspace directory.

    PBI Desktop may store the project path in workspace metadata files.
    We also scan common locations for .pbip files.
    """
    # Check for workspace.json or similar metadata that may contain the project path
    for meta_file in ws_dir.glob("*.json"):
        try:
            import json
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            # Look for project path references in metadata
            for key in ("ProjectPath", "projectPath", "SourcePath", "sourcePath"):
                if key in data and isinstance(data[key], str):
                    candidate = Path(data[key])
                    if candidate.exists():
                        return _resolve_tmdl_from_pbip(candidate)
        except (json.JSONDecodeError, OSError, KeyError):
            continue

    return None


def _resolve_tmdl_from_pbip(path: Path) -> Path | None:
    """Given a .pbip file or project directory, find the TMDL definition folder."""
    if path.is_file() and path.suffix == ".pbip":
        path = path.parent

    # Look for SemanticModel/definition pattern
    for sm_dir in path.glob("*.SemanticModel"):
        defn = sm_dir / "definition"
        if defn.exists():
            return defn
        if (sm_dir / "model.tmdl").exists():
            return sm_dir

    # Maybe path itself is a TMDL folder
    if (path / "model.tmdl").exists():
        return path

    return None
