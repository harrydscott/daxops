"""FastAPI app factory for the DaxOps web app."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from daxops import __version__
from daxops.app.routes import info, score, check, scan, settings, fix, connection, document


STATIC_DIR = Path(__file__).parent / "static"


def create_app(
    model_path: str | None = None,
    ssas_server: str | None = None,
    ssas_database: str | None = None,
) -> FastAPI:
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
    app.include_router(fix.router, prefix="/api")
    app.include_router(connection.router, prefix="/api")
    app.include_router(document.router, prefix="/api")

    # WebSocket for progress updates
    @app.websocket("/ws/progress")
    async def websocket_progress(ws: WebSocket):
        """WebSocket endpoint for real-time generation progress."""
        await ws.accept()
        from daxops.app.routes.document import _ai_config, _get_api_key, _staged, DescriptionItem, DescriptionStatus
        from daxops.document.generator import find_undocumented, generate_description
        try:
            while True:
                data = await ws.receive_json()
                action = data.get("action")
                if action == "generate":
                    object_paths = data.get("object_paths")
                    from daxops.app.state import app_state as _state
                    model = _state.ensure_model()
                    undoc = find_undocumented(model)
                    if object_paths:
                        paths_set = set(object_paths)
                        undoc = [o for o in undoc if o.object_path in paths_set]

                    provider = _ai_config["provider"]
                    api_key = _get_api_key(provider)
                    llm_model = _ai_config["llm_model"]
                    kwargs = {}
                    if provider == "azure_openai" and _ai_config.get("azure_endpoint"):
                        kwargs["azure_endpoint"] = _ai_config["azure_endpoint"]

                    total = len(undoc)
                    await ws.send_json({"type": "start", "total": total})

                    for i, obj in enumerate(undoc):
                        try:
                            result = generate_description(obj, provider, llm_model, api_key, **kwargs)
                            item = DescriptionItem(
                                object_type=obj.object_type,
                                object_path=obj.object_path,
                                name=obj.name,
                                table_name=obj.table_name,
                                expression=obj.expression,
                                data_type=obj.data_type,
                                description=result.description,
                                status=DescriptionStatus.GENERATED,
                            )
                        except Exception as e:
                            item = DescriptionItem(
                                object_type=obj.object_type,
                                object_path=obj.object_path,
                                name=obj.name,
                                table_name=obj.table_name,
                                expression=obj.expression,
                                data_type=obj.data_type,
                                description=f"Error: {e}",
                                status=DescriptionStatus.NOT_GENERATED,
                            )
                        _staged[obj.object_path] = item
                        await ws.send_json({
                            "type": "progress",
                            "current": i + 1,
                            "total": total,
                            "item": item.model_dump(),
                        })

                    await ws.send_json({"type": "complete", "total": total})
        except WebSocketDisconnect:
            pass

    # Configure state
    from daxops.app.state import app_state

    if ssas_server and ssas_database:
        app_state.set_ssas(ssas_server, ssas_database)

        # Try to auto-detect TMDL folder for hybrid mode
        if not model_path:
            from daxops.ssas import find_workspace_tmdl
            detected = find_workspace_tmdl(ssas_server)
            if detected:
                model_path = str(detected)

    if model_path:
        app_state.set_model_path(model_path)

    # Serve static files (frontend)
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app
