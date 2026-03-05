"""Auto-fix mode — applies safe fixes to TMDL models."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from daxops.models.schema import SemanticModel


@dataclass
class FixResult:
    """A single fix applied to the model."""
    rule: str
    file_path: str
    description: str
    applied: bool = True


def run_fixes(model_path: str | Path, dry_run: bool = False) -> list[FixResult]:
    """Run all auto-fixes on a TMDL model directory.

    Returns a list of fixes that were applied (or would be applied in dry-run mode).
    """
    from daxops.parser.tmdl import resolve_model_root

    root = resolve_model_root(model_path)
    results: list[FixResult] = []

    tables_dir = root / "tables"
    if tables_dir.is_dir():
        for tf in sorted(tables_dir.glob("*.tmdl")):
            results.extend(_fix_table_file(tf, dry_run))

    return results


def _fix_table_file(path: Path, dry_run: bool) -> list[FixResult]:
    """Apply fixes to a single table TMDL file."""
    results: list[FixResult] = []
    content = path.read_text(encoding="utf-8")
    original = content

    # Fix 1: Rename dim/fact/stg prefixes in table names
    content, prefix_fixes = _fix_table_prefix(content, path)
    results.extend(prefix_fixes)

    # Fix 2: Hide key columns (columns ending in ID, Key, SK)
    content, hidden_fixes = _fix_hidden_keys(content, path)
    results.extend(hidden_fixes)

    # Fix 3: Add isHidden to key columns that don't have it
    # (handled in _fix_hidden_keys above)

    if content != original and not dry_run:
        path.write_text(content, encoding="utf-8")
        # If table was renamed, rename the file too
        for fix in prefix_fixes:
            if fix.rule == "RENAME_TABLE_FILE":
                new_name = fix.description.split(" -> ")[1]
                new_path = path.parent / f"{new_name}.tmdl"
                if not new_path.exists():
                    path.rename(new_path)
                    fix.file_path = str(new_path)

    if content == original:
        for fix in results:
            fix.applied = False

    return results


def _fix_table_prefix(content: str, path: Path) -> tuple[str, list[FixResult]]:
    """Remove dim/fact/stg/vw/tbl/dbo prefixes from table name declarations."""
    results: list[FixResult] = []

    # Match the table declaration line
    m = re.match(r"^(table\s+)(['\"]?)(.+?)\2\s*$", content.split("\n")[0])
    if not m:
        return content, results

    table_name = m.group(3)
    prefix_match = re.match(r"^(dim|fact|stg|vw|tbl|dbo)[_.]?(.+)$", table_name, re.IGNORECASE)
    if not prefix_match:
        return content, results

    new_name = prefix_match.group(2)
    # Capitalize first letter
    if new_name and new_name[0].islower():
        new_name = new_name[0].upper() + new_name[1:]

    old_line = content.split("\n")[0]
    quote = m.group(2) or "'"
    new_line = f"table {quote}{new_name}{quote}"
    content = content.replace(old_line, new_line, 1)

    results.append(FixResult(
        rule="NAMING_CONVENTION",
        file_path=str(path),
        description=f"Renamed table '{table_name}' -> '{new_name}'",
    ))

    # Track file rename needed
    old_stem = path.stem
    if old_stem.lower() != new_name.lower():
        results.append(FixResult(
            rule="RENAME_TABLE_FILE",
            file_path=str(path),
            description=f"{old_stem} -> {new_name}",
        ))

    return content, results


def _fix_hidden_keys(content: str, path: Path) -> tuple[str, list[FixResult]]:
    """Add isHidden to key columns that aren't hidden."""
    results: list[FixResult] = []
    lines = content.split("\n")
    new_lines: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Detect column declaration
        col_match = re.match(r"^(\s*)column\s+'([^']+)'(.*)$", line)
        if not col_match:
            col_match = re.match(r"^(\s*)column\s+(\S+)(.*)$", line)

        if col_match:
            indent = col_match.group(1)
            col_name = col_match.group(2).strip("'\"")
            is_key = bool(re.search(r"(ID|Key|SK)$", col_name))

            if is_key:
                # Check if isHidden already exists in the column block
                new_lines.append(line)
                i += 1
                has_hidden = False
                col_block_lines: list[str] = []

                while i < len(lines):
                    inner = lines[i].strip()
                    # End of column block: next column, measure, partition, hierarchy, or table-level
                    if (inner.startswith("column ") or inner.startswith("measure ") or
                            inner.startswith("partition ") or inner.startswith("hierarchy ") or
                            inner.startswith("///") and i + 1 < len(lines) and
                            (lines[i + 1].strip().startswith("column ") or
                             lines[i + 1].strip().startswith("measure "))):
                        break
                    if inner == "isHidden":
                        has_hidden = True
                    col_block_lines.append(lines[i])
                    i += 1

                if not has_hidden:
                    # Insert isHidden after the column declaration
                    prop_indent = indent + "\t"
                    if col_block_lines:
                        # Use the indent of the first property
                        first_prop = col_block_lines[0]
                        prop_indent = first_prop[:len(first_prop) - len(first_prop.lstrip())]
                    new_lines.append(f"{prop_indent}isHidden")
                    results.append(FixResult(
                        rule="HIDDEN_KEYS",
                        file_path=str(path),
                        description=f"Added isHidden to column '{col_name}'",
                    ))

                new_lines.extend(col_block_lines)
                continue

        new_lines.append(line)
        i += 1

    return "\n".join(new_lines), results
