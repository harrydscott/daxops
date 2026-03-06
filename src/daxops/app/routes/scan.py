"""POST /api/scan — re-scan the model."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from daxops.app.state import app_state

router = APIRouter()


class ScanResponse(BaseModel):
    status: str
    model_name: str
    tables: int
    measures: int
    connection_mode: str


@router.post("/scan", response_model=ScanResponse)
def post_scan() -> ScanResponse:
    """Re-scan the model from disk or SSAS."""
    if app_state.connection_mode == "none":
        raise HTTPException(status_code=400, detail="No model path or SSAS connection configured")
    model = app_state.scan()
    return ScanResponse(
        status="ok",
        model_name=model.name,
        tables=len(model.tables),
        measures=sum(len(t.measures) for t in model.tables),
        connection_mode=app_state.connection_mode,
    )
