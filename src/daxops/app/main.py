"""FastAPI app factory for the DaxOps web app."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from daxops import __version__
from daxops.app.routes import info, score, check, scan, settings


STATIC_DIR = Path(__file__).parent / "static"


def create_app(model_path: str | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="DaxOps",
        version=__version__,
        description="Semantic Model Lifecycle Tool for Power BI / Microsoft Fabric",
    )

    # Register API routes
    app.include_router(info.router, prefix="/api")
    app.include_router(score.router, prefix="/api")
    app.include_router(check.router, prefix="/api")
    app.include_router(scan.router, prefix="/api")
    app.include_router(settings.router, prefix="/api")

    # Set initial model path if provided
    if model_path:
        from daxops.app.state import app_state
        app_state.set_model_path(model_path)

    # Serve static files (frontend)
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app
