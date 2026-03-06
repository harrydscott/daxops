"""GET /api/info — model statistics."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from daxops.app.state import app_state

router = APIRouter()


class TableDetail(BaseModel):
    name: str
    columns: int
    measures: int
    partitions: int
    has_description: bool


class InfoResponse(BaseModel):
    name: str
    culture: str | None
    tables: int
    columns: int
    hidden_columns: int
    calculated_columns: int
    measures: int
    measures_with_description: int
    relationships: int
    bidirectional_relationships: int
    roles: int
    table_details: list[TableDetail]


@router.get("/info", response_model=InfoResponse)
def get_info() -> InfoResponse:
    """Return model statistics."""
    if not app_state.model_path:
        raise HTTPException(status_code=400, detail="No model path configured")
    model = app_state.ensure_model()
    return InfoResponse(
        name=model.name,
        culture=model.culture,
        tables=len(model.tables),
        columns=sum(len(t.columns) for t in model.tables),
        hidden_columns=sum(1 for t in model.tables for c in t.columns if c.is_hidden),
        calculated_columns=sum(1 for t in model.tables for c in t.columns if c.expression),
        measures=sum(len(t.measures) for t in model.tables),
        measures_with_description=sum(1 for t in model.tables for m in t.measures if m.description),
        relationships=len(model.relationships),
        bidirectional_relationships=sum(1 for r in model.relationships if r.cross_filtering == "both"),
        roles=len(model.roles),
        table_details=[
            TableDetail(
                name=t.name,
                columns=len(t.columns),
                measures=len(t.measures),
                partitions=len(t.partitions),
                has_description=bool(t.description),
            )
            for t in model.tables
        ],
    )
