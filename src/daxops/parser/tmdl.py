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


def _unquote(name: str) -> str:
    """Strip surrounding single/double quotes from a name."""
    return name.strip("'\" ")


def resolve_model_root(path: str | Path) -> Path:
    """Resolve the TMDL model root directory from a path.

    Accepts:
    - A raw TMDL folder (contains model.tmdl and/or tables/)
    - A .pbip project root (contains *.pbip file + *.SemanticModel/ folder)
    - A *.SemanticModel folder directly
    - A definition/ subfolder within a SemanticModel folder

    Returns the directory containing model.tmdl and tables/.
    """
    root = Path(path)
    if not root.is_dir():
        raise ValueError(f"Path is not a directory: {root}")

    # Case 1: Direct TMDL folder (has model.tmdl or tables/)
    if (root / "model.tmdl").exists() or (root / "tables").is_dir():
        return root

    # Case 2: .pbip project root — look for *.SemanticModel folder
    pbip_files = list(root.glob("*.pbip"))
    semantic_dirs = list(root.glob("*.SemanticModel"))
    if pbip_files or semantic_dirs:
        for sd in semantic_dirs:
            if sd.is_dir():
                # Check definition/ subfolder first (TMDL format)
                defn = sd / "definition"
                if defn.is_dir() and ((defn / "model.tmdl").exists() or (defn / "tables").is_dir()):
                    return defn
                # Fall back to SemanticModel root
                if (sd / "model.tmdl").exists() or (sd / "tables").is_dir():
                    return sd
        if pbip_files:
            raise ValueError(
                f"Found .pbip file but no SemanticModel folder with TMDL content in: {root}"
            )

    # Case 3: This IS a *.SemanticModel folder
    if root.name.endswith(".SemanticModel"):
        defn = root / "definition"
        if defn.is_dir() and ((defn / "model.tmdl").exists() or (defn / "tables").is_dir()):
            return defn
        if (root / "model.tmdl").exists() or (root / "tables").is_dir():
            return root

    raise ValueError(
        f"Cannot find TMDL model in: {root}. "
        "Expected a folder with model.tmdl/tables/, a .pbip project, or a .SemanticModel folder."
    )


def parse_model(model_path: str | Path) -> SemanticModel:
    """Parse a TMDL model directory and return a SemanticModel.

    Accepts a raw TMDL folder, a .pbip project root, or a .SemanticModel folder.
    """
    root = resolve_model_root(model_path)
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
            model.name = _unquote(stripped.split("model ", 1)[1])
        elif stripped.startswith("culture:"):
            model.culture = stripped.split(":", 1)[1].strip()


def _parse_table_file(path: Path) -> Table | None:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return None

    table = Table(name="")
    pending_desc: list[str] = []
    current_obj: str = ""  # "column", "measure", "partition", "hierarchy"
    current_column: Column | None = None
    current_measure: Measure | None = None
    current_partition: Partition | None = None
    in_partition_source = False
    partition_source_lines: list[str] = []
    in_measure_continuation = False
    measure_expr_lines: list[str] = []
    in_backtick_block = False  # for ``` delimited expressions
    in_extended_property = False  # for extendedProperty blocks

    def _flush():
        nonlocal current_column, current_measure, current_partition
        nonlocal in_partition_source, partition_source_lines
        nonlocal in_measure_continuation, measure_expr_lines
        nonlocal in_backtick_block, in_extended_property
        if current_column:
            table.columns.append(current_column)
            current_column = None
        if current_measure:
            if measure_expr_lines:
                # Append continuation lines to the expression
                full_expr = current_measure.expression
                if full_expr:
                    full_expr += "\n"
                full_expr += "\n".join(measure_expr_lines)
                current_measure.expression = full_expr.strip()
                measure_expr_lines = []
            table.measures.append(current_measure)
            current_measure = None
        if current_partition:
            if partition_source_lines:
                current_partition.source = "\n".join(partition_source_lines)
                partition_source_lines = []
            table.partitions.append(current_partition)
            current_partition = None
        in_partition_source = False
        in_measure_continuation = False
        in_backtick_block = False
        in_extended_property = False

    for line in lines:
        stripped = line.strip()

        # Backtick-delimited expression block
        if in_backtick_block:
            if stripped.startswith("```") or stripped.endswith("```"):
                # End of backtick block — extract any content before the closing ```
                content = stripped.replace("```", "").strip()
                if content:
                    measure_expr_lines.append(content)
                in_backtick_block = False
            else:
                measure_expr_lines.append(stripped)
            continue

        # Extended property / annotation block (JSON or multi-line value — skip)
        if in_extended_property:
            # End when we hit a line at the same or lower indent level that is a property
            if _is_known_property(stripped) or re.match(r"^\s*(measure|column|partition|hierarchy|table)\s+", line):
                in_extended_property = False
                # Fall through to normal parsing
            else:
                continue

        # Description comments (/// above an object)
        if stripped.startswith("///"):
            pending_desc.append(stripped[3:].strip())
            continue

        # Table declaration
        m = re.match(r"^table\s+['\"]?(.+?)['\"]?\s*$", stripped)
        if m and not table.name:
            table.name = _unquote(m.group(1))
            if pending_desc:
                table.description = " ".join(pending_desc)
                pending_desc = []
            continue

        # Table lineageTag (only when no current object)
        if stripped.startswith("lineageTag:") and current_obj == "":
            table.lineage_tag = stripped.split(":", 1)[1].strip()
            continue

        # Measure: 'Name' = expression OR measure Name = expression (unquoted)
        m = re.match(r"^\s*measure\s+'([^']+)'\s*=\s*(.*)?$", stripped)
        if not m:
            m = re.match(r"^\s*measure\s+(\S+)\s*=\s*(.*)?$", stripped)
        if m:
            _flush()
            current_obj = "measure"
            expr = (m.group(2) or "").strip()
            # Handle backtick-delimited expressions
            if expr.startswith("```"):
                expr = expr[3:].strip()
                if expr.endswith("```"):
                    expr = expr[:-3].strip()
                else:
                    in_backtick_block = True
            current_measure = Measure(name=_unquote(m.group(1)), expression=expr)
            if pending_desc:
                current_measure.description = " ".join(pending_desc)
                pending_desc = []
            # If the expression is empty or doesn't look complete, prepare for continuation
            if not expr and not in_backtick_block:
                in_measure_continuation = True
            continue

        # Column with calculated expression: column 'Name' = expression
        m = re.match(r"^\s*column\s+'([^']+)'\s*=\s*(.+)$", stripped)
        if not m:
            m = re.match(r"^\s*column\s+(\S+)\s*=\s*(.+)$", stripped)
        if m:
            _flush()
            current_obj = "column"
            current_column = Column(name=_unquote(m.group(1)), expression=m.group(2).strip())
            if pending_desc:
                current_column.description = " ".join(pending_desc)
                pending_desc = []
            continue

        # Column (regular, no expression)
        m = re.match(r"^\s*column\s+'([^']+)'\s*$", stripped)
        if not m:
            m = re.match(r"^\s*column\s+(\S+)\s*$", stripped)
        if m:
            _flush()
            current_obj = "column"
            current_column = Column(name=_unquote(m.group(1)))
            if pending_desc:
                current_column.description = " ".join(pending_desc)
                pending_desc = []
            continue

        # Hierarchy — skip hierarchy blocks (just track that we're in one)
        m = re.match(r"^\s*hierarchy\s+", stripped)
        if m:
            _flush()
            current_obj = "hierarchy"
            pending_desc = []
            continue

        # Partition
        m = re.match(r"^\s*partition\s+'([^']+)'\s*=\s*\w+", stripped)
        if not m:
            m = re.match(r"^\s*partition\s+(\S+)\s*=\s*\w+", stripped)
        if m:
            _flush()
            current_obj = "partition"
            current_partition = Partition(name=_unquote(m.group(1)))
            pending_desc = []
            continue

        # Properties on current object
        if current_obj == "hierarchy":
            # Skip hierarchy child lines (level, column:, lineageTag:)
            pending_desc = []
            continue

        # Multi-line measure expression continuation
        if in_measure_continuation and current_measure:
            # Check if this line is a known property (not expression continuation)
            if _is_known_property(stripped):
                in_measure_continuation = False
                # Fall through to property parsing below
            else:
                measure_expr_lines.append(stripped)
                pending_desc = []
                continue

        if stripped.startswith("dataType:") and current_column:
            current_column.data_type = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("formatString:"):
            val = stripped.split(":", 1)[1].strip()
            if current_column:
                current_column.format_string = val
            elif current_measure:
                in_measure_continuation = False
                current_measure.format_string = val
        elif stripped == "isHidden":
            if current_column:
                current_column.is_hidden = True
            # Measures can also be hidden (we don't track it but must not break parsing)
        elif stripped.startswith("summarizeBy:") and current_column:
            current_column.summarize_by = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("lineageTag:"):
            val = stripped.split(":", 1)[1].strip()
            if current_column:
                current_column.lineage_tag = val
            elif current_measure:
                in_measure_continuation = False
                current_measure.lineage_tag = val
            elif current_obj == "":
                table.lineage_tag = val
        elif stripped.startswith("displayFolder:"):
            val = stripped.split(":", 1)[1].strip()
            if current_measure:
                in_measure_continuation = False
                current_measure.display_folder = val
            elif current_column:
                current_column.display_folder = val
        elif stripped.startswith("mode:") and current_partition:
            current_partition.mode = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("source") and stripped.endswith("=") and current_partition:
            in_partition_source = True
        elif in_partition_source and current_partition:
            partition_source_lines.append(line)
        elif stripped.startswith("extendedProperty ") or stripped.startswith("annotation "):
            # Skip extended property / annotation blocks (may be multi-line JSON)
            if "=" in stripped and not stripped.rstrip().endswith("="):
                pass  # single-line annotation, skip
            elif "=" in stripped:
                in_extended_property = True  # multi-line block, skip until next property
        elif stripped.startswith("changedProperty ") or stripped.startswith("excludeFromModelRefresh"):
            pass  # single-line properties, skip
        elif stripped.startswith("sourceColumn:"):
            pass  # skip sourceColumn

        # Clear pending desc if we hit a non-desc, non-object line
        if not stripped.startswith("///"):
            pending_desc = []

    _flush()
    return table if table.name else None


def _is_known_property(stripped: str) -> bool:
    """Check if a line is a known TMDL property (not DAX expression continuation)."""
    props = [
        "formatString:", "displayFolder:", "lineageTag:", "dataType:",
        "summarizeBy:", "isHidden", "mode:", "source", "description:",
        "annotation ", "extendedProperty ", "changedProperty ",
        "sourceColumn:", "sortByColumn:", "isDataTypeInferred",
        "isNameInferred", "isAvailableInMDX", "excludeFromModelRefresh",
        "isDefaultLabel", "isDefaultImage", "isKey", "isNullable",
        "isPrivate", "isUnique",
    ]
    return any(stripped.startswith(p) for p in props)


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
                # Handle quoted table names: 'Table Name'.Column
                m2 = re.match(r"'([^']+)'\.(.+)", raw)
                if m2:
                    current.from_table = m2.group(1)
                    current.from_column = _unquote(m2.group(2))
                else:
                    parts = raw.split(".")
                    if len(parts) == 2:
                        current.from_table = _unquote(parts[0])
                        current.from_column = _unquote(parts[1])
            elif stripped.startswith("toColumn:"):
                raw = stripped.split(":", 1)[1].strip()
                m2 = re.match(r"'([^']+)'\.(.+)", raw)
                if m2:
                    current.to_table = m2.group(1)
                    current.to_column = _unquote(m2.group(2))
                else:
                    parts = raw.split(".")
                    if len(parts) == 2:
                        current.to_table = _unquote(parts[0])
                        current.to_column = _unquote(parts[1])
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
        if current_table and stripped and not stripped.startswith("tablePermission") and not stripped.startswith("modelPermission"):
            if current_table not in role.filter_expressions:
                role.filter_expressions[current_table] = stripped
        pending_desc = []

    return role if role.name else None
