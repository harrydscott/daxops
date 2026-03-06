"""XMLA endpoint scanner — connect to Power BI service and pull model metadata.

Converts live Power BI / Fabric dataset metadata into the same SemanticModel
used by the TMDL parser, so all scoring, health checks, and reporting work
identically on live models.

Requires one of:
  pip install daxops[xmla]   # pyadomd + azure-identity
  pip install daxops[fabric] # sempy-fabric
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from daxops.models.schema import (
    Column,
    Measure,
    Partition,
    Relationship,
    SemanticModel,
    Table,
)


@dataclass
class XmlaConnection:
    """Connection parameters for XMLA endpoint."""

    workspace: str
    dataset: str
    connection_string: str = ""
    tenant_id: str = ""
    client_id: str = ""
    client_secret: str = ""

    def build_connection_string(self) -> str:
        """Build XMLA connection string from parameters."""
        if self.connection_string:
            return self.connection_string
        server = f"powerbi://api.powerbi.com/v1.0/myorg/{self.workspace}"
        return f"Provider=MSOLAP;Data Source={server};Initial Catalog={self.dataset}"


# ── DMV Queries ─────────────────────────────────────────────────────────
# These are the Discovery Management Views used to extract model metadata.

DMV_TABLES = "SELECT * FROM $SYSTEM.TMSCHEMA_TABLES"
DMV_COLUMNS = "SELECT * FROM $SYSTEM.TMSCHEMA_COLUMNS"
DMV_MEASURES = "SELECT * FROM $SYSTEM.TMSCHEMA_MEASURES"
DMV_RELATIONSHIPS = "SELECT * FROM $SYSTEM.TMSCHEMA_RELATIONSHIPS"
DMV_PARTITIONS = "SELECT * FROM $SYSTEM.TMSCHEMA_PARTITIONS"


def _query_dmv(connection: Any, query: str) -> list[dict[str, Any]]:
    """Execute a DMV query and return rows as list of dicts."""
    cursor = connection.cursor()
    cursor.execute(query)
    columns = [desc[0] for desc in cursor.description]
    rows = []
    for row in cursor.fetchall():
        rows.append(dict(zip(columns, row)))
    cursor.close()
    return rows


def scan_xmla(conn: XmlaConnection) -> SemanticModel:
    """Scan a Power BI dataset via XMLA and return a SemanticModel.

    Tries pyadomd first, falls back to sempy-fabric.

    Raises:
        ImportError: If neither pyadomd nor sempy is installed.
        ConnectionError: If the connection fails.
    """
    connection = _connect(conn)
    try:
        return _build_model_from_dmv(connection, conn.dataset)
    finally:
        connection.close()


def _connect(conn: XmlaConnection) -> Any:
    """Establish connection via pyadomd or sempy."""
    # Try pyadomd first
    try:
        from pyadomd import Pyadomd  # type: ignore[import-untyped]

        cs = conn.build_connection_string()
        return Pyadomd(cs)
    except ImportError:
        pass

    # Try sempy-fabric
    try:
        from sempy import fabric  # type: ignore[import-untyped]

        return fabric.connect(conn.workspace, conn.dataset)
    except ImportError:
        pass

    raise ImportError(
        "XMLA scanning requires pyadomd or sempy-fabric. Install with:\n"
        "  pip install daxops[xmla]    # for pyadomd + azure-identity\n"
        "  pip install daxops[fabric]  # for sempy-fabric"
    )


def _build_model_from_dmv(connection: Any, dataset_name: str) -> SemanticModel:
    """Query DMV views and build a SemanticModel."""
    raw_tables = _query_dmv(connection, DMV_TABLES)
    raw_columns = _query_dmv(connection, DMV_COLUMNS)
    raw_measures = _query_dmv(connection, DMV_MEASURES)
    raw_relationships = _query_dmv(connection, DMV_RELATIONSHIPS)
    raw_partitions = _query_dmv(connection, DMV_PARTITIONS)

    return build_model_from_metadata(
        dataset_name, raw_tables, raw_columns, raw_measures,
        raw_relationships, raw_partitions,
    )


def build_model_from_metadata(
    dataset_name: str,
    raw_tables: list[dict[str, Any]],
    raw_columns: list[dict[str, Any]],
    raw_measures: list[dict[str, Any]],
    raw_relationships: list[dict[str, Any]],
    raw_partitions: list[dict[str, Any]],
) -> SemanticModel:
    """Convert raw DMV metadata dicts into a SemanticModel.

    This is the core conversion logic, separated from the connection layer
    so it can be tested independently with mock data.
    """
    # Index columns, measures, partitions by TableID
    cols_by_table: dict[int, list[dict]] = {}
    for c in raw_columns:
        tid = c.get("TableID", 0)
        cols_by_table.setdefault(tid, []).append(c)

    measures_by_table: dict[int, list[dict]] = {}
    for m in raw_measures:
        tid = m.get("TableID", 0)
        measures_by_table.setdefault(tid, []).append(m)

    parts_by_table: dict[int, list[dict]] = {}
    for p in raw_partitions:
        tid = p.get("TableID", 0)
        parts_by_table.setdefault(tid, []).append(p)

    # Build tables
    tables = []
    table_id_to_name: dict[int, str] = {}
    for t in raw_tables:
        tid = t.get("ID", 0)
        name = t.get("Name", "")
        table_id_to_name[tid] = name

        columns = [
            Column(
                name=c.get("ExplicitName") or c.get("Name", ""),
                data_type=_map_data_type(c.get("ExplicitDataType", c.get("DataType", 0))),
                format_string=c.get("FormatString", "") or "",
                is_hidden=bool(c.get("IsHidden", False)),
                description=c.get("Description", "") or "",
                display_folder=c.get("DisplayFolder", "") or "",
                expression=c.get("Expression", "") or "",
            )
            for c in cols_by_table.get(tid, [])
            if c.get("Type", 0) != 3  # skip RowNumber columns
        ]

        measures = [
            Measure(
                name=m.get("Name", ""),
                expression=m.get("Expression", "") or "",
                format_string=m.get("FormatString", "") or "",
                description=m.get("Description", "") or "",
                display_folder=m.get("DisplayFolder", "") or "",
            )
            for m in measures_by_table.get(tid, [])
        ]

        partitions = [
            Partition(
                name=p.get("Name", ""),
                mode=_map_partition_mode(p.get("Mode", 0)),
                source=p.get("QueryDefinition", "") or "",
            )
            for p in parts_by_table.get(tid, [])
        ]

        tables.append(Table(
            name=name,
            description=t.get("Description", "") or "",
            columns=columns,
            measures=measures,
            partitions=partitions,
        ))

    # Build relationships
    relationships = []
    for r in raw_relationships:
        from_tid = r.get("FromTableID", 0)
        to_tid = r.get("ToTableID", 0)
        cross = "both" if r.get("CrossFilteringBehavior", 1) == 2 else "single"
        relationships.append(Relationship(
            name=r.get("Name", ""),
            from_table=table_id_to_name.get(from_tid, ""),
            from_column=r.get("FromColumnID_Name", r.get("FromColumn", "")),
            to_table=table_id_to_name.get(to_tid, ""),
            to_column=r.get("ToColumnID_Name", r.get("ToColumn", "")),
            cross_filtering=cross,
        ))

    return SemanticModel(
        name=dataset_name,
        tables=tables,
        relationships=relationships,
    )


# ── Data type mapping ───────────────────────────────────────────────────

_DATA_TYPE_MAP = {
    0: "",           # Unknown
    1: "string",
    2: "int64",
    3: "int64",
    4: "int64",
    5: "int64",
    6: "double",
    7: "double",
    8: "boolean",
    9: "dateTime",
    10: "string",    # Binary → string
    11: "decimal",
    17: "string",    # Variant
}


def _map_data_type(raw: Any) -> str:
    """Map XMLA numeric DataType to TMDL string."""
    if isinstance(raw, str):
        return raw.lower()
    return _DATA_TYPE_MAP.get(int(raw) if raw else 0, "")


_PARTITION_MODE_MAP = {
    0: "import",
    1: "directQuery",
    2: "dual",
    3: "push",
}


def _map_partition_mode(raw: Any) -> str:
    """Map XMLA numeric partition Mode to string."""
    if isinstance(raw, str):
        return raw.lower()
    return _PARTITION_MODE_MAP.get(int(raw) if raw else 0, "import")
