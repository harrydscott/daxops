"""GET /api/fix/preview and POST /api/fix/apply — fix workflow endpoints."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from daxops.app.state import app_state

router = APIRouter()

# Rules that have auto-fix support in fix.py
FIXABLE_RULES = {"NAMING_CONVENTION", "HIDDEN_KEYS"}


class FixPreviewItem(BaseModel):
    rule: str
    file_path: str
    description: str
    before: str
    after: str


class ManualFixItem(BaseModel):
    rule: str
    object_path: str
    message: str
    recommendation: str | None


class FixPreviewResponse(BaseModel):
    fixable: list[FixPreviewItem]
    manual: list[ManualFixItem]
    summary: dict


class FixApplyRequest(BaseModel):
    selected: list[int] | None = None  # indices into the fixable list; None = all


class FixApplyResponse(BaseModel):
    applied: int
    files_changed: int
    backup_path: str | None
    message: str


class UndoResponse(BaseModel):
    restored: list[str]
    message: str


class BackupEntry(BaseModel):
    timestamp: str
    file_count: int


class BackupsResponse(BaseModel):
    backups: list[BackupEntry]


def _generate_previews(model_path: str) -> list[FixPreviewItem]:
    """Generate before/after diffs by running fixes in dry-run mode on temp copies."""
    import shutil
    import tempfile

    from daxops.parser.tmdl import resolve_model_root
    from daxops.fix import run_fixes

    root = resolve_model_root(model_path)
    previews: list[FixPreviewItem] = []

    # For each table file, compute what would change
    tables_dir = root / "tables"
    if not tables_dir.is_dir():
        return previews

    for tf in sorted(tables_dir.glob("*.tmdl")):
        before_content = tf.read_text(encoding="utf-8")

        # Create a temp copy to apply fixes
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            tmp_tables = tmp_root / "tables"
            tmp_tables.mkdir(parents=True)
            # Copy model.tmdl if it exists (needed by resolve_model_root)
            model_tmdl = root / "model.tmdl"
            if model_tmdl.exists():
                shutil.copy2(model_tmdl, tmp_root / "model.tmdl")
            # Copy this single table file
            tmp_file = tmp_tables / tf.name
            shutil.copy2(tf, tmp_file)

            # Run fixes on the temp copy (not dry-run — we want to see actual changes)
            from daxops.fix import _fix_table_file
            results = _fix_table_file(tmp_file, dry_run=False)

            if results and any(r.applied for r in results):
                # Check if file was renamed
                after_file = tmp_file
                for r in results:
                    if r.rule == "RENAME_TABLE_FILE":
                        new_name = r.description.split(" -> ")[1]
                        candidate = tmp_tables / f"{new_name}.tmdl"
                        if candidate.exists():
                            after_file = candidate
                            break

                after_content = after_file.read_text(encoding="utf-8")

                for r in results:
                    if r.rule == "RENAME_TABLE_FILE":
                        continue  # File rename is part of NAMING_CONVENTION
                    if r.applied:
                        previews.append(FixPreviewItem(
                            rule=r.rule,
                            file_path=str(tf),
                            description=r.description,
                            before=before_content,
                            after=after_content,
                        ))

    return previews


@router.get("/fix/preview", response_model=FixPreviewResponse)
def get_fix_preview() -> FixPreviewResponse:
    """Dry-run showing before/after diffs for each fixable finding."""
    if not app_state.model_path:
        raise HTTPException(status_code=400, detail="No model path configured")
    app_state.ensure_model()

    fixable = _generate_previews(app_state.model_path)

    # Get manual-only findings (non-fixable rules)
    from daxops.health.rules import run_health_checks
    model = app_state.ensure_model()
    all_findings = run_health_checks(model)
    config = app_state.config
    if config.exclude_rules:
        all_findings = [f for f in all_findings if f.rule not in config.exclude_rules]

    manual = [
        ManualFixItem(
            rule=f.rule,
            object_path=f.object_path,
            message=f.message,
            recommendation=f.recommendation,
        )
        for f in all_findings
        if f.rule not in FIXABLE_RULES
    ]

    return FixPreviewResponse(
        fixable=fixable,
        manual=manual,
        summary={
            "fixable_count": len(fixable),
            "manual_count": len(manual),
            "files_affected": len(set(f.file_path for f in fixable)),
        },
    )


@router.post("/fix/apply", response_model=FixApplyResponse)
def post_fix_apply(req: FixApplyRequest = FixApplyRequest()) -> FixApplyResponse:
    """Apply selected fixes to TMDL files on disk."""
    if not app_state.model_path:
        raise HTTPException(status_code=400, detail="No model path configured")

    # Generate previews to know what files will be affected
    previews = _generate_previews(app_state.model_path)
    if not previews:
        return FixApplyResponse(
            applied=0, files_changed=0, backup_path=None,
            message="No fixes to apply.",
        )

    # Filter to selected indices
    if req.selected is not None:
        selected = [previews[i] for i in req.selected if 0 <= i < len(previews)]
    else:
        selected = previews

    if not selected:
        return FixApplyResponse(
            applied=0, files_changed=0, backup_path=None,
            message="No fixes selected.",
        )

    # Determine files to back up
    from daxops.parser.tmdl import resolve_model_root
    affected_files = list(set(Path(p.file_path) for p in selected))

    # Create backup
    from daxops.app.backup import create_backup
    backup_path = create_backup(app_state.model_path, affected_files)

    # Apply fixes
    from daxops.fix import run_fixes
    results = run_fixes(app_state.model_path, dry_run=False)
    applied_count = sum(1 for r in results if r.applied and r.rule != "RENAME_TABLE_FILE")
    files_changed = len(set(r.file_path for r in results if r.applied))

    # Re-scan model after fixes
    app_state.scan()

    return FixApplyResponse(
        applied=applied_count,
        files_changed=files_changed,
        backup_path=str(backup_path) if backup_path else None,
        message=f"Applied {applied_count} fixes to {files_changed} files.",
    )


@router.post("/fix/undo", response_model=UndoResponse)
def post_fix_undo() -> UndoResponse:
    """Restore files from the most recent backup."""
    if not app_state.model_path:
        raise HTTPException(status_code=400, detail="No model path configured")

    from daxops.app.backup import restore_latest
    restored = restore_latest(app_state.model_path)

    if not restored:
        raise HTTPException(status_code=404, detail="No backups available to restore.")

    # Re-scan after undo
    app_state.scan()

    return UndoResponse(
        restored=restored,
        message=f"Restored {len(restored)} files from backup.",
    )


@router.get("/fix/backups", response_model=BackupsResponse)
def get_backups() -> BackupsResponse:
    """List available backups."""
    if not app_state.model_path:
        raise HTTPException(status_code=400, detail="No model path configured")

    from daxops.app.backup import list_backups
    backups = list_backups(app_state.model_path)

    return BackupsResponse(
        backups=[
            BackupEntry(timestamp=b["timestamp"], file_count=b["file_count"])
            for b in backups
        ]
    )
