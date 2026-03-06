"""GET /api/connection — connection status and mode information."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from daxops.app.state import app_state

router = APIRouter()


class ConnectionResponse(BaseModel):
    mode: str
    ssas_server: str | None
    ssas_database: str | None
    model_path: str | None
    can_write: bool


@router.get("/connection", response_model=ConnectionResponse)
def get_connection() -> ConnectionResponse:
    """Return current connection mode and status."""
    mode = app_state.connection_mode
    return ConnectionResponse(
        mode=mode,
        ssas_server=app_state.ssas_server,
        ssas_database=app_state.ssas_database,
        model_path=app_state.model_path,
        can_write=app_state.model_path is not None,
    )
