"""Semantic-aware model diff engine."""
from __future__ import annotations

from dataclasses import dataclass, field

from daxops.models.schema import SemanticModel


@dataclass
class Change:
    category: str  # table, column, measure, relationship
    change_type: str  # added, removed, modified
    path: str
    details: str = ""


@dataclass
class DiffResult:
    changes: list[Change] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return len(self.changes) > 0


def diff_models(old: SemanticModel, new: SemanticModel) -> DiffResult:
    result = DiffResult()
    _diff_tables(old, new, result)
    _diff_relationships(old, new, result)
    return result


def _diff_tables(old: SemanticModel, new: SemanticModel, result: DiffResult):
    old_tables = {t.name: t for t in old.tables}
    new_tables = {t.name: t for t in new.tables}

    for name in sorted(set(old_tables) | set(new_tables)):
        if name not in old_tables:
            result.changes.append(Change("table", "added", name))
            # All columns/measures are implicitly added
            for c in new_tables[name].columns:
                result.changes.append(Change("column", "added", f"{name}.{c.name}"))
            for m in new_tables[name].measures:
                result.changes.append(Change("measure", "added", f"{name}.[{m.name}]"))
        elif name not in new_tables:
            result.changes.append(Change("table", "removed", name))
        else:
            _diff_columns(old_tables[name], new_tables[name], result)
            _diff_measures(old_tables[name], new_tables[name], result)
            # Table description change
            if old_tables[name].description != new_tables[name].description:
                result.changes.append(Change("table", "modified", name, "description changed"))


def _diff_columns(old_table, new_table, result: DiffResult):
    old_cols = {c.name: c for c in old_table.columns}
    new_cols = {c.name: c for c in new_table.columns}
    tname = old_table.name

    for name in sorted(set(old_cols) | set(new_cols)):
        if name not in old_cols:
            result.changes.append(Change("column", "added", f"{tname}.{name}"))
        elif name not in new_cols:
            result.changes.append(Change("column", "removed", f"{tname}.{name}"))
        else:
            diffs = []
            oc, nc = old_cols[name], new_cols[name]
            if oc.data_type != nc.data_type:
                diffs.append(f"dataType: {oc.data_type} → {nc.data_type}")
            if oc.is_hidden != nc.is_hidden:
                diffs.append(f"isHidden: {oc.is_hidden} → {nc.is_hidden}")
            if oc.format_string != nc.format_string:
                diffs.append(f"formatString changed")
            if oc.description != nc.description:
                diffs.append("description changed")
            if diffs:
                result.changes.append(Change("column", "modified", f"{tname}.{name}", "; ".join(diffs)))


def _diff_measures(old_table, new_table, result: DiffResult):
    old_m = {m.name: m for m in old_table.measures}
    new_m = {m.name: m for m in new_table.measures}
    tname = old_table.name

    for name in sorted(set(old_m) | set(new_m)):
        if name not in old_m:
            result.changes.append(Change("measure", "added", f"{tname}.[{name}]"))
        elif name not in new_m:
            result.changes.append(Change("measure", "removed", f"{tname}.[{name}]"))
        else:
            diffs = []
            om, nm = old_m[name], new_m[name]
            if om.expression != nm.expression:
                diffs.append(f"DAX changed")
            if om.description != nm.description:
                diffs.append("description changed")
            if om.format_string != nm.format_string:
                diffs.append("formatString changed")
            if diffs:
                result.changes.append(Change("measure", "modified", f"{tname}.[{name}]", "; ".join(diffs)))


def _diff_relationships(old: SemanticModel, new: SemanticModel, result: DiffResult):
    old_r = {r.name: r for r in old.relationships}
    new_r = {r.name: r for r in new.relationships}

    for name in sorted(set(old_r) | set(new_r)):
        if name not in old_r:
            result.changes.append(Change("relationship", "added", name))
        elif name not in new_r:
            result.changes.append(Change("relationship", "removed", name))
        else:
            orr, nrr = old_r[name], new_r[name]
            diffs = []
            if (orr.from_table, orr.from_column) != (nrr.from_table, nrr.from_column):
                diffs.append("fromColumn changed")
            if (orr.to_table, orr.to_column) != (nrr.to_table, nrr.to_column):
                diffs.append("toColumn changed")
            if orr.cross_filtering != nrr.cross_filtering:
                diffs.append(f"crossFiltering: {orr.cross_filtering} → {nrr.cross_filtering}")
            if diffs:
                result.changes.append(Change("relationship", "modified", name, "; ".join(diffs)))
