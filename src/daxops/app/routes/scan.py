"""POST /api/scan — re-scan the model from disk."""
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


@router.post("/scan", response_model=ScanResponse)
def post_scan() -> ScanResponse:
    """Re-scan the model from disk."""
    if not app_state.model_path:
        raise HTTPException(status_code=400, detail="No model path configured")
    model = app_state.scan()
    return ScanResponse(
        status="ok",
        model_name=model.name,
        tables=len(model.tables),
        measures=sum(len(t.measures) for t in model.tables),
    )
