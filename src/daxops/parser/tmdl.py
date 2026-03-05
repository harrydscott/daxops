"""TMDL file parser — reads a TMDL model directory into a SemanticModel."""
from __future__ import annotations

import re
from pathlib import Path

from daxops.models.schema import (
    Column,
    Measure,
    Partition,
    Relationship,
    Role,
    SemanticModel,
    Table,
)


def parse_model(model_path: str | Path) -> SemanticModel:
    """Parse a TMDL model directory and return a SemanticModel."""
    root = Path(model_path)
    model = SemanticModel()

    # Parse model.tmdl
    model_file = root / "model.tmdl"
    if model_file.exists():
        _parse_model_file(model_file, model)

    # Parse tables
    tables_dir = root / "tables"
    if tables_dir.is_dir():
        for tf in sorted(tables_dir.glob("*.tmdl")):
            table = _parse_table_file(tf)
            if table:
                model.tables.append(table)

    # Parse relationships
    rel_file = root / "relationships.tmdl"
    if rel_file.exists():
        model.relationships = _parse_relationships_file(rel_file)

    # Parse roles
    roles_dir = root / "roles"
    if roles_dir.is_dir():
        for rf in sorted(roles_dir.glob("*.tmdl")):
            role = _parse_role_file(rf)
            if role:
                model.roles.append(role)

    return model


def _parse_model_file(path: Path, model: SemanticModel) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("model "):
            model.name = stripped.split("model ", 1)[1].strip()
        elif stripped.startswith("culture:"):
            model.culture = stripped.split(":", 1)[1].strip()


def _parse_table_file(path: Path) -> Table | None:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return None

    table = Table(name="")
    pending_desc: list[str] = []
    current_obj: str = ""  # "column", "measure", "partition"
    current_column: Column | None = None
    current_measure: Measure | None = None
    current_partition: Partition | None = None
    in_partition_source = False
    partition_source_lines: list[str] = []

    def _flush():
        nonlocal current_column, current_measure, current_partition
        nonlocal in_partition_source, partition_source_lines
        if current_column:
            table.columns.append(current_column)
            current_column = None
        if current_measure:
            table.measures.append(current_measure)
            current_measure = None
        if current_partition:
            if partition_source_lines:
                current_partition.source = "\n".join(partition_source_lines)
                partition_source_lines = []
            table.partitions.append(current_partition)
            current_partition = None
        in_partition_source = False

    for line in lines:
        stripped = line.strip()

        # Description comments (/// above an object)
        if stripped.startswith("///"):
            pending_desc.append(stripped[3:].strip())
            continue

        # Table declaration
        m = re.match(r"^table\s+['\"]?(.+?)['\"]?\s*$", stripped)
        if m and not table.name:
            table.name = m.group(1).strip("'\"")
            if pending_desc:
                table.description = " ".join(pending_desc)
                pending_desc = []
            continue

        # Table lineageTag
        if stripped.startswith("lineageTag:") and current_obj == "":
            table.lineage_tag = stripped.split(":", 1)[1].strip()
            continue

        # Measure
        m = re.match(r"^\s*measure\s+'([^']+)'\s*=\s*(.*)$", stripped)
        if m:
            _flush()
            current_obj = "measure"
            current_measure = Measure(name=m.group(1), expression=m.group(2).strip())
            if pending_desc:
                current_measure.description = " ".join(pending_desc)
                pending_desc = []
            continue

        # Column
        m = re.match(r"^\s*column\s+'?([^']+?)'?\s*$", stripped)
        if m:
            _flush()
            current_obj = "column"
            current_column = Column(name=m.group(1).strip("'\""))
            if pending_desc:
                current_column.description = " ".join(pending_desc)
                pending_desc = []
            continue

        # Partition
        m = re.match(r"^\s*partition\s+'?([^'=]+?)'?\s*=\s*\w+", stripped)
        if not m:
            m = re.match(r"^\s*partition\s+(.+?)\s*=\s*\w+", stripped)
        if m:
            _flush()
            current_obj = "partition"
            current_partition = Partition(name=m.group(1).strip("'\" "))
            pending_desc = []
            continue

        # Properties on current object
        if stripped.startswith("dataType:") and current_column:
            current_column.data_type = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("formatString:"):
            val = stripped.split(":", 1)[1].strip()
            if current_column:
                current_column.format_string = val
            elif current_measure:
                current_measure.format_string = val
        elif stripped == "isHidden" and current_column:
            current_column.is_hidden = True
        elif stripped.startswith("summarizeBy:") and current_column:
            current_column.summarize_by = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("lineageTag:"):
            val = stripped.split(":", 1)[1].strip()
            if current_column:
                current_column.lineage_tag = val
            elif current_measure:
                current_measure.lineage_tag = val
            elif current_obj == "":
                table.lineage_tag = val
        elif stripped.startswith("displayFolder:"):
            val = stripped.split(":", 1)[1].strip()
            if current_measure:
                current_measure.display_folder = val
            elif current_column:
                current_column.display_folder = val
        elif stripped.startswith("mode:") and current_partition:
            current_partition.mode = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("source") and stripped.endswith("=") and current_partition:
            in_partition_source = True
        elif in_partition_source and current_partition:
            partition_source_lines.append(line)

        # Clear pending desc if we hit a non-desc, non-object line
        if not stripped.startswith("///"):
            pending_desc = []

    _flush()
    return table if table.name else None


def _parse_relationships_file(path: Path) -> list[Relationship]:
    lines = path.read_text(encoding="utf-8").splitlines()
    rels: list[Relationship] = []
    current: Relationship | None = None

    for line in lines:
        stripped = line.strip()

        m = re.match(r"^relationship\s+(\S+)", stripped)
        if m:
            if current:
                rels.append(current)
            current = Relationship(name=m.group(1))
            continue

        if current:
            if stripped.startswith("fromColumn:"):
                raw = stripped.split(":", 1)[1].strip()
                parts = raw.split(".")
                if len(parts) == 2:
                    current.from_table = parts[0].strip("'\" ")
                    current.from_column = parts[1].strip("'\" ")
            elif stripped.startswith("toColumn:"):
                raw = stripped.split(":", 1)[1].strip()
                parts = raw.split(".")
                if len(parts) == 2:
                    current.to_table = parts[0].strip("'\" ")
                    current.to_column = parts[1].strip("'\" ")
            elif stripped.startswith("crossFilteringBehavior:"):
                val = stripped.split(":", 1)[1].strip().lower()
                if "both" in val:
                    current.cross_filtering = "both"

    if current:
        rels.append(current)
    return rels


def _parse_role_file(path: Path) -> Role | None:
    lines = path.read_text(encoding="utf-8").splitlines()
    role = Role(name="")
    pending_desc: list[str] = []
    current_table = ""

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("///"):
            pending_desc.append(stripped[3:].strip())
            continue
        m = re.match(r"^role\s+'?([^']+?)'?\s*$", stripped)
        if m:
            role.name = m.group(1)
            if pending_desc:
                role.description = " ".join(pending_desc)
                pending_desc = []
            continue
        m = re.match(r"tablePermission\s+'?([^'=]+?)'?\s*=", stripped)
        if m:
            current_table = m.group(1).strip()
        # Simple: capture filter expression lines
        if current_table and stripped and not stripped.startswith("tablePermission"):
            if current_table not in role.filter_expressions:
                role.filter_expressions[current_table] = stripped
        pending_desc = []

    return role if role.name else None
