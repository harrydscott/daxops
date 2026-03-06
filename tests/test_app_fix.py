"""Tests for fix workflow endpoints and backup system."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daxops.app.backup import (
    BACKUP_DIR_NAME,
    MAX_BACKUPS,
    create_backup,
    list_backups,
    restore_latest,
    ensure_gitignore,
)
from daxops.app.main import create_app
from daxops.app.state import app_state

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_MODEL = str(FIXTURES / "sample-model")


@pytest.fixture(autouse=True)
def reset_state():
    """Reset app state between tests."""
    app_state.model_path = None
    app_state.model = None
    from daxops.config import DaxOpsConfig
    app_state.config = DaxOpsConfig()
    yield


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


@pytest.fixture
def client_with_model():
    app = create_app(model_path=SAMPLE_MODEL)
    return TestClient(app)


@pytest.fixture
def tmp_model(tmp_path):
    """Copy sample model to a temp dir so we can modify it."""
    dest = tmp_path / "test-model"
    shutil.copytree(FIXTURES / "sample-model", dest)
    return dest


@pytest.fixture
def client_with_tmp_model(tmp_model):
    """TestClient with a writable temp copy of the model."""
    app = create_app(model_path=str(tmp_model))
    return TestClient(app), tmp_model


# ---- Backup System ----

class TestBackupSystem:
    def test_create_backup(self, tmp_model):
        files = list((tmp_model / "tables").glob("*.tmdl"))[:2]
        backup_dir = create_backup(str(tmp_model), files)
        assert backup_dir is not None
        assert backup_dir.exists()
        assert BACKUP_DIR_NAME in str(backup_dir)
        backed_up = list(backup_dir.rglob("*"))
        assert any(f.is_file() for f in backed_up)

    def test_create_backup_empty(self, tmp_model):
        result = create_backup(str(tmp_model), [])
        assert result is None

    def test_restore_latest(self, tmp_model):
        # Back up a file, modify it, then restore
        table_file = next((tmp_model / "tables").glob("*.tmdl"))
        original_content = table_file.read_text()
        create_backup(str(tmp_model), [table_file])
        table_file.write_text("modified content")
        assert table_file.read_text() == "modified content"

        restored = restore_latest(str(tmp_model))
        assert len(restored) > 0
        assert table_file.read_text() == original_content

    def test_restore_removes_backup(self, tmp_model):
        files = list((tmp_model / "tables").glob("*.tmdl"))[:1]
        create_backup(str(tmp_model), files)
        backups_before = list_backups(str(tmp_model))
        assert len(backups_before) == 1
        restore_latest(str(tmp_model))
        backups_after = list_backups(str(tmp_model))
        assert len(backups_after) == 0

    def test_restore_no_backups(self, tmp_model):
        restored = restore_latest(str(tmp_model))
        assert restored == []

    def test_prune_old_backups(self, tmp_model):
        files = list((tmp_model / "tables").glob("*.tmdl"))[:1]
        for i in range(MAX_BACKUPS + 3):
            import time
            create_backup(str(tmp_model), files)
            time.sleep(0.01)  # ensure unique timestamps
        backups = list_backups(str(tmp_model))
        assert len(backups) <= MAX_BACKUPS

    def test_list_backups(self, tmp_model):
        files = list((tmp_model / "tables").glob("*.tmdl"))[:1]
        create_backup(str(tmp_model), files)
        backups = list_backups(str(tmp_model))
        assert len(backups) == 1
        assert "timestamp" in backups[0]
        assert "file_count" in backups[0]
        assert backups[0]["file_count"] >= 1

    def test_ensure_gitignore_creates(self, tmp_model):
        gitignore = tmp_model / ".gitignore"
        if gitignore.exists():
            gitignore.unlink()
        ensure_gitignore(str(tmp_model))
        assert gitignore.exists()
        assert ".daxops-backup/" in gitignore.read_text()

    def test_ensure_gitignore_no_duplicate(self, tmp_model):
        gitignore = tmp_model / ".gitignore"
        gitignore.write_text(".daxops-backup/\n")
        ensure_gitignore(str(tmp_model))
        content = gitignore.read_text()
        assert content.count(".daxops-backup/") == 1


# ---- Fix Preview Endpoint ----

class TestFixPreview:
    def test_preview_no_model(self, client):
        resp = client.get("/api/fix/preview")
        assert resp.status_code == 400

    def test_preview_with_model(self, client_with_model):
        resp = client_with_model.get("/api/fix/preview")
        assert resp.status_code == 200
        data = resp.json()
        assert "fixable" in data
        assert "manual" in data
        assert "summary" in data

    def test_preview_fixable_items(self, client_with_model):
        data = client_with_model.get("/api/fix/preview").json()
        # sample-model has fixable findings
        assert len(data["fixable"]) > 0
        item = data["fixable"][0]
        assert "rule" in item
        assert "file_path" in item
        assert "description" in item
        assert "before" in item
        assert "after" in item
        assert item["before"] != item["after"]

    def test_preview_manual_items(self, client_with_model):
        data = client_with_model.get("/api/fix/preview").json()
        # There should be manual-fix findings too
        assert len(data["manual"]) > 0
        item = data["manual"][0]
        assert "rule" in item
        assert "object_path" in item

    def test_preview_summary(self, client_with_model):
        data = client_with_model.get("/api/fix/preview").json()
        s = data["summary"]
        assert s["fixable_count"] == len(data["fixable"])
        assert s["manual_count"] == len(data["manual"])
        assert "files_affected" in s


# ---- Fix Apply Endpoint ----

class TestFixApply:
    def test_apply_no_model(self, client):
        resp = client.post("/api/fix/apply")
        assert resp.status_code == 400

    def test_apply_all(self, client_with_tmp_model):
        client, tmp_model = client_with_tmp_model
        resp = client.post("/api/fix/apply", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["applied"] > 0
        assert data["files_changed"] > 0
        assert data["backup_path"] is not None
        assert "Applied" in data["message"]

    def test_apply_creates_backup(self, client_with_tmp_model):
        client, tmp_model = client_with_tmp_model
        client.post("/api/fix/apply", json={})
        backup_dir = tmp_model / BACKUP_DIR_NAME
        assert backup_dir.exists()
        backups = list(backup_dir.iterdir())
        assert len(backups) > 0

    def test_apply_selected(self, client_with_tmp_model):
        client, tmp_model = client_with_tmp_model
        # Get preview first
        preview = client.get("/api/fix/preview").json()
        if len(preview["fixable"]) > 1:
            resp = client.post("/api/fix/apply", json={"selected": [0]})
            assert resp.status_code == 200

    def test_apply_rescans(self, client_with_tmp_model):
        client, _ = client_with_tmp_model
        client.post("/api/fix/apply", json={})
        # Model should be re-scanned
        assert app_state.model is not None


# ---- Fix Undo Endpoint ----

class TestFixUndo:
    def test_undo_no_model(self, client):
        resp = client.post("/api/fix/undo")
        assert resp.status_code == 400

    def test_undo_no_backups(self, client_with_tmp_model):
        client, _ = client_with_tmp_model
        resp = client.post("/api/fix/undo")
        assert resp.status_code == 404

    def test_undo_after_apply(self, client_with_tmp_model):
        client, tmp_model = client_with_tmp_model
        # Save original content of a table file
        table_files = list((tmp_model / "tables").glob("*.tmdl"))
        originals = {str(f): f.read_text() for f in table_files}

        # Apply fixes
        client.post("/api/fix/apply", json={})

        # Undo
        resp = client.post("/api/fix/undo")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["restored"]) > 0
        assert "Restored" in data["message"]

        # Check files are back to original
        for f in table_files:
            if str(f) in originals:
                assert f.read_text() == originals[str(f)]


# ---- Fix Backups Endpoint ----

class TestFixBackups:
    def test_backups_no_model(self, client):
        resp = client.get("/api/fix/backups")
        assert resp.status_code == 400

    def test_backups_empty(self, client_with_tmp_model):
        client, _ = client_with_tmp_model
        resp = client.get("/api/fix/backups")
        assert resp.status_code == 200
        assert resp.json()["backups"] == []

    def test_backups_after_apply(self, client_with_tmp_model):
        client, _ = client_with_tmp_model
        client.post("/api/fix/apply", json={})
        resp = client.get("/api/fix/backups")
        assert resp.status_code == 200
        backups = resp.json()["backups"]
        assert len(backups) >= 1
        assert "timestamp" in backups[0]
        assert "file_count" in backups[0]
