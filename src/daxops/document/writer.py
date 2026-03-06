"""Write descriptions back to TMDL files."""
from __future__ import annotations

import re
from pathlib import Path

from daxops.parser.tmdl import resolve_model_root


def write_descriptions(
    model_path: str,
    descriptions: list[dict],
) -> list[str]:
    """Write approved descriptions to TMDL files.

    Args:
        model_path: Path to the model root.
        descriptions: List of dicts with keys: object_type, object_path, description.

    Returns:
        List of file paths that were modified.
    """
    root = resolve_model_root(model_path)
    tables_dir = root / "tables"
    modified_files: set[str] = set()

    # Group descriptions by table
    by_table: dict[str, list[dict]] = {}
    for desc in descriptions:
        table_name = _extract_table_name(desc["object_path"], desc["object_type"])
        by_table.setdefault(table_name, []).append(desc)

    for table_name, descs in by_table.items():
        tmdl_file = _find_table_file(tables_dir, table_name)
        if not tmdl_file:
            continue

        content = tmdl_file.read_text(encoding="utf-8")
        for desc in descs:
            content = _insert_description(content, desc)

        tmdl_file.write_text(content, encoding="utf-8")
        modified_files.add(str(tmdl_file))

    return sorted(modified_files)


def _extract_table_name(object_path: str, object_type: str) -> str:
    """Extract table name from an object path."""
    if object_type == "table":
        return object_path
    # "TableName.[MeasureName]" or "TableName.ColumnName"
    return object_path.split(".")[0]


def _find_table_file(tables_dir: Path, table_name: str) -> Path | None:
    """Find the TMDL file for a given table name."""
    if not tables_dir.is_dir():
        return None
    # Try exact match first, then case-insensitive
    for f in tables_dir.glob("*.tmdl"):
        if f.stem == table_name:
            return f
    for f in tables_dir.glob("*.tmdl"):
        if f.stem.lower() == table_name.lower():
            return f
    return None


def _insert_description(content: str, desc: dict) -> str:
    """Insert a /// description line before the object declaration in TMDL content."""
    obj_type = desc["object_type"]
    obj_path = desc["object_path"]
    description = desc["description"]

    # Clean up description — remove any /// prefix if user included it
    description = description.strip()
    if description.startswith("///"):
        description = description[3:].strip()

    if obj_type == "table":
        # Insert before "table TableName"
        pattern = re.compile(r"^(table\s+.*)", re.MULTILINE)
        match = pattern.search(content)
        if match:
            line_start = match.start()
            # Check if there's already a /// description before this line
            before = content[:line_start]
            if before.rstrip().endswith("///"):
                return content  # Already has a description marker
            # Check for existing /// comment on previous line
            lines = content[:line_start].split("\n")
            if lines and lines[-1].strip().startswith("///"):
                return content  # Already described
            content = content[:line_start] + f"/// {description}\n" + content[line_start:]
    elif obj_type == "measure":
        # Extract measure name from path "Table.[MeasureName]"
        measure_name = obj_path.split(".[")[1].rstrip("]") if ".[" in obj_path else obj_path.split(".")[-1]
        content = _insert_before_object(content, "measure", measure_name, description)
    elif obj_type == "column":
        col_name = obj_path.split(".")[-1]
        content = _insert_before_object(content, "column", col_name, description)

    return content


def _insert_before_object(content: str, keyword: str, name: str, description: str) -> str:
    """Insert a /// line before a 'measure' or 'column' declaration."""
    # Match both quoted and unquoted names
    escaped = re.escape(name)
    # Try quoted version first: measure 'Name' or column 'Name'
    patterns = [
        re.compile(rf"^(\t{keyword}\s+'{escaped}')", re.MULTILINE),
        re.compile(rf"^(\t{keyword}\s+{escaped})\b", re.MULTILINE),
    ]

    for pattern in patterns:
        match = pattern.search(content)
        if match:
            line_start = match.start()
            # Check if previous line already has a /// description
            before = content[:line_start]
            prev_lines = before.rstrip("\n").split("\n")
            if prev_lines and prev_lines[-1].strip().startswith("///"):
                return content  # Already described

            content = content[:line_start] + f"\t/// {description}\n" + content[line_start:]
            return content

    return content
