"""AI Description Editor endpoints — generate, approve, write descriptions."""
from __future__ import annotations

from enum import Enum

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from daxops.app.state import app_state

router = APIRouter()


# --- AI Provider Settings ---

class ProviderConfig(BaseModel):
    provider: str  # openai, azure_openai, anthropic
    llm_model: str | None = None
    azure_endpoint: str | None = None


class ProviderSettingsResponse(BaseModel):
    provider: str
    llm_model: str
    has_api_key: bool
    azure_endpoint: str | None = None


class SetApiKeyRequest(BaseModel):
    provider: str
    api_key: str


class TestConnectionResponse(BaseModel):
    success: bool
    message: str


# In-memory AI provider state (not persisted in .daxops.yml for security)
_ai_config = {
    "provider": "openai",
    "llm_model": "gpt-4o",
    "azure_endpoint": None,
}


def _get_api_key(provider: str) -> str | None:
    """Get API key from keyring, falling back gracefully."""
    try:
        from daxops.document.keystore import get_api_key
        return get_api_key(provider)
    except RuntimeError:
        return None


@router.get("/ai/settings", response_model=ProviderSettingsResponse)
def get_ai_settings() -> ProviderSettingsResponse:
    """Return current AI provider configuration."""
    from daxops.document.generator import DEFAULT_MODELS
    provider = _ai_config["provider"]
    model = _ai_config["llm_model"] or DEFAULT_MODELS.get(provider, "gpt-4o")
    return ProviderSettingsResponse(
        provider=provider,
        llm_model=model,
        has_api_key=_get_api_key(provider) is not None,
        azure_endpoint=_ai_config.get("azure_endpoint"),
    )


@router.put("/ai/settings", response_model=ProviderSettingsResponse)
def set_ai_settings(req: ProviderConfig) -> ProviderSettingsResponse:
    """Update AI provider configuration."""
    from daxops.document.generator import SUPPORTED_PROVIDERS, DEFAULT_MODELS
    if req.provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {req.provider}")
    _ai_config["provider"] = req.provider
    _ai_config["llm_model"] = req.llm_model or DEFAULT_MODELS.get(req.provider, "gpt-4o")
    if req.azure_endpoint:
        _ai_config["azure_endpoint"] = req.azure_endpoint
    return get_ai_settings()


@router.post("/ai/key", response_model=ProviderSettingsResponse)
def set_api_key(req: SetApiKeyRequest) -> ProviderSettingsResponse:
    """Store an API key in the OS keychain."""
    try:
        from daxops.document.keystore import store_api_key
        store_api_key(req.provider, req.api_key)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return get_ai_settings()


@router.delete("/ai/key/{provider}", response_model=ProviderSettingsResponse)
def delete_api_key_endpoint(provider: str) -> ProviderSettingsResponse:
    """Remove an API key from the OS keychain."""
    try:
        from daxops.document.keystore import delete_api_key
        delete_api_key(provider)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return get_ai_settings()


@router.post("/ai/test", response_model=TestConnectionResponse)
def test_ai_connection() -> TestConnectionResponse:
    """Test the current AI provider connection."""
    from daxops.document.generator import test_connection
    provider = _ai_config["provider"]
    api_key = _get_api_key(provider)
    model = _ai_config["llm_model"]
    kwargs = {}
    if provider == "azure_openai" and _ai_config.get("azure_endpoint"):
        kwargs["azure_endpoint"] = _ai_config["azure_endpoint"]
    try:
        result = test_connection(provider, api_key, model, **kwargs)
        return TestConnectionResponse(success=True, message=result)
    except Exception as e:
        return TestConnectionResponse(success=False, message=str(e))


# --- Document Generation ---

class DescriptionStatus(str, Enum):
    NOT_GENERATED = "not_generated"
    GENERATED = "generated"
    EDITED = "edited"
    APPROVED = "approved"
    WRITTEN = "written"


class DescriptionItem(BaseModel):
    object_type: str
    object_path: str
    name: str
    table_name: str
    expression: str | None = None
    data_type: str | None = None
    description: str | None = None
    status: DescriptionStatus = DescriptionStatus.NOT_GENERATED


class UndocumentedResponse(BaseModel):
    objects: list[DescriptionItem]
    total: int


class GenerateRequest(BaseModel):
    object_paths: list[str] | None = None  # None = all undocumented


class GenerateResponse(BaseModel):
    generated: list[DescriptionItem]
    total: int


class UpdateDescriptionRequest(BaseModel):
    object_path: str
    description: str
    status: DescriptionStatus


class ApproveRequest(BaseModel):
    object_paths: list[str]  # paths to approve


class WriteRequest(BaseModel):
    object_paths: list[str] | None = None  # None = all approved


class WriteResponse(BaseModel):
    written: int
    files_modified: list[str]
    backup_path: str | None = None
    message: str


# In-memory staged descriptions
_staged: dict[str, DescriptionItem] = {}


def _reset_staged():
    """Reset staged descriptions (for testing)."""
    _staged.clear()


@router.get("/document/undocumented", response_model=UndocumentedResponse)
def get_undocumented() -> UndocumentedResponse:
    """List all undocumented objects in the model."""
    if app_state.connection_mode == "none":
        raise HTTPException(status_code=400, detail="No model path or SSAS connection configured")
    model = app_state.ensure_model()
    from daxops.document.generator import find_undocumented
    undoc = find_undocumented(model)
    items = []
    for obj in undoc:
        # Check if we have a staged description
        if obj.object_path in _staged:
            items.append(_staged[obj.object_path])
        else:
            items.append(DescriptionItem(
                object_type=obj.object_type,
                object_path=obj.object_path,
                name=obj.name,
                table_name=obj.table_name,
                expression=obj.expression,
                data_type=obj.data_type,
            ))
    return UndocumentedResponse(objects=items, total=len(items))


@router.post("/document/generate", response_model=GenerateResponse)
def generate_descriptions_endpoint(req: GenerateRequest) -> GenerateResponse:
    """Generate AI descriptions for selected undocumented objects."""
    if app_state.connection_mode == "none":
        raise HTTPException(status_code=400, detail="No model path or SSAS connection configured")
    model = app_state.ensure_model()
    from daxops.document.generator import find_undocumented, generate_description

    undoc = find_undocumented(model)

    # Filter to requested objects
    if req.object_paths:
        paths_set = set(req.object_paths)
        undoc = [o for o in undoc if o.object_path in paths_set]

    if not undoc:
        return GenerateResponse(generated=[], total=0)

    provider = _ai_config["provider"]
    api_key = _get_api_key(provider)
    llm_model = _ai_config["llm_model"]
    kwargs = {}
    if provider == "azure_openai" and _ai_config.get("azure_endpoint"):
        kwargs["azure_endpoint"] = _ai_config["azure_endpoint"]

    generated: list[DescriptionItem] = []
    for obj in undoc:
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
        generated.append(item)

    return GenerateResponse(generated=generated, total=len(generated))


@router.put("/document/description", response_model=DescriptionItem)
def update_description(req: UpdateDescriptionRequest) -> DescriptionItem:
    """Update a staged description (edit or change status)."""
    if req.object_path not in _staged:
        raise HTTPException(status_code=404, detail=f"No staged description for: {req.object_path}")
    item = _staged[req.object_path]
    item.description = req.description
    item.status = req.status
    return item


@router.post("/document/approve", response_model=list[DescriptionItem])
def approve_descriptions(req: ApproveRequest) -> list[DescriptionItem]:
    """Bulk approve staged descriptions."""
    approved = []
    for path in req.object_paths:
        if path in _staged:
            item = _staged[path]
            if item.status in (DescriptionStatus.GENERATED, DescriptionStatus.EDITED):
                item.status = DescriptionStatus.APPROVED
                approved.append(item)
    return approved


@router.post("/document/write", response_model=WriteResponse)
def write_descriptions_endpoint(req: WriteRequest) -> WriteResponse:
    """Write approved descriptions to TMDL files on disk."""
    if not app_state.model_path:
        raise HTTPException(status_code=400, detail="No model path configured")

    # Collect approved descriptions
    if req.object_paths:
        paths = req.object_paths
    else:
        paths = [p for p, item in _staged.items() if item.status == DescriptionStatus.APPROVED]

    to_write = []
    for path in paths:
        item = _staged.get(path)
        if not item or item.status != DescriptionStatus.APPROVED:
            continue
        if not item.description:
            continue
        to_write.append({
            "object_type": item.object_type,
            "object_path": item.object_path,
            "description": item.description,
        })

    if not to_write:
        return WriteResponse(written=0, files_modified=[], message="No approved descriptions to write.")

    # Create backup before writing
    from daxops.document.writer import write_descriptions
    from daxops.app.backup import create_backup
    from daxops.parser.tmdl import resolve_model_root

    root = resolve_model_root(app_state.model_path)
    tables_dir = root / "tables"
    affected_files = list(tables_dir.glob("*.tmdl")) if tables_dir.is_dir() else []
    backup_path = create_backup(app_state.model_path, affected_files)

    files_modified = write_descriptions(app_state.model_path, to_write)

    # Update staged status
    for desc in to_write:
        path = desc["object_path"]
        if path in _staged:
            _staged[path].status = DescriptionStatus.WRITTEN

    # Re-scan model
    app_state.scan()

    return WriteResponse(
        written=len(to_write),
        files_modified=files_modified,
        backup_path=str(backup_path) if backup_path else None,
        message=f"Wrote {len(to_write)} descriptions to {len(files_modified)} files.",
    )


@router.get("/document/staged", response_model=list[DescriptionItem])
def get_staged() -> list[DescriptionItem]:
    """Return all staged descriptions."""
    return list(_staged.values())
