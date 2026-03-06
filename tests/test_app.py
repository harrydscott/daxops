"""Tests for the DaxOps web app (FastAPI endpoints)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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
    """TestClient with no model pre-loaded."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def client_with_model():
    """TestClient with sample model pre-loaded."""
    app = create_app(model_path=SAMPLE_MODEL)
    return TestClient(app)


# ---- /api/info ----

class TestInfoEndpoint:
    def test_info_no_model(self, client):
        resp = client.get("/api/info")
        assert resp.status_code == 400
        assert "No model path" in resp.json()["detail"]

    def test_info_with_model(self, client_with_model):
        resp = client_with_model.get("/api/info")
        assert resp.status_code == 200
        data = resp.json()
        assert "name" in data
        assert "tables" in data
        assert isinstance(data["tables"], int)
        assert isinstance(data["table_details"], list)
        assert data["tables"] == len(data["table_details"])

    def test_info_fields(self, client_with_model):
        data = client_with_model.get("/api/info").json()
        expected_fields = [
            "name", "culture", "tables", "columns", "hidden_columns",
            "calculated_columns", "measures", "measures_with_description",
            "relationships", "bidirectional_relationships", "roles",
        ]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"


# ---- /api/score ----

class TestScoreEndpoint:
    def test_score_no_model(self, client):
        resp = client.get("/api/score")
        assert resp.status_code == 400

    def test_score_with_model(self, client_with_model):
        resp = client_with_model.get("/api/score")
        assert resp.status_code == 200
        data = resp.json()
        assert "bronze" in data
        assert "silver" in data
        assert "gold" in data
        assert "summary" in data

    def test_score_summary_fields(self, client_with_model):
        summary = client_with_model.get("/api/score").json()["summary"]
        assert "bronze_score" in summary
        assert "silver_score" in summary
        assert "gold_score" in summary
        assert "bronze_pass" in summary
        assert "tier" in summary
        assert summary["tier"] in ("gold", "silver", "bronze", "none")
        assert "thresholds" in summary

    def test_score_criteria_structure(self, client_with_model):
        data = client_with_model.get("/api/score").json()
        for tier in ("bronze", "silver", "gold"):
            assert isinstance(data[tier], list)
            if data[tier]:
                c = data[tier][0]
                assert "name" in c
                assert "score" in c
                assert "max_score" in c
                assert "details" in c


# ---- /api/check ----

class TestCheckEndpoint:
    def test_check_no_model(self, client):
        resp = client.get("/api/check")
        assert resp.status_code == 400

    def test_check_with_model(self, client_with_model):
        resp = client_with_model.get("/api/check")
        assert resp.status_code == 200
        data = resp.json()
        assert "findings" in data
        assert "summary" in data
        assert isinstance(data["findings"], list)

    def test_check_summary_counts(self, client_with_model):
        data = client_with_model.get("/api/check").json()
        s = data["summary"]
        assert s["total"] == len(data["findings"])
        assert s["total"] == s["errors"] + s["warnings"] + s["info"]

    def test_check_finding_structure(self, client_with_model):
        data = client_with_model.get("/api/check").json()
        if data["findings"]:
            f = data["findings"][0]
            assert "rule" in f
            assert "severity" in f
            assert "message" in f
            assert "object_path" in f

    def test_check_filter_severity(self, client_with_model):
        all_data = client_with_model.get("/api/check").json()
        err_data = client_with_model.get("/api/check?severity=ERROR").json()
        # Errors-only should be <= total
        assert len(err_data["findings"]) <= len(all_data["findings"])
        for f in err_data["findings"]:
            assert f["severity"] == "ERROR"

    def test_check_filter_rule(self, client_with_model):
        all_data = client_with_model.get("/api/check").json()
        if all_data["findings"]:
            rule = all_data["findings"][0]["rule"]
            filtered = client_with_model.get(f"/api/check?rule={rule}").json()
            assert all(f["rule"] == rule for f in filtered["findings"])

    def test_check_filter_search(self, client_with_model):
        all_data = client_with_model.get("/api/check").json()
        if all_data["findings"]:
            # Search for part of first finding's object path
            term = all_data["findings"][0]["object_path"][:5]
            filtered = client_with_model.get(f"/api/check?search={term}").json()
            assert len(filtered["findings"]) >= 1


# ---- /api/scan ----

class TestScanEndpoint:
    def test_scan_no_model(self, client):
        resp = client.post("/api/scan")
        assert resp.status_code == 400

    def test_scan_with_model(self, client_with_model):
        resp = client_with_model.post("/api/scan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "model_name" in data
        assert "tables" in data
        assert "measures" in data


# ---- /api/settings ----

class TestSettingsEndpoint:
    def test_get_settings_empty(self, client):
        resp = client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["model_path"] is None
        assert data["model_loaded"] is False

    def test_get_settings_with_model(self, client_with_model):
        resp = client_with_model.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["model_path"] == SAMPLE_MODEL

    def test_set_model_path(self, client):
        resp = client.put(
            "/api/settings/model-path",
            json={"model_path": SAMPLE_MODEL},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["model_path"] == SAMPLE_MODEL
        assert data["model_loaded"] is True

    def test_set_model_path_invalid(self, client):
        resp = client.put(
            "/api/settings/model-path",
            json={"model_path": "/nonexistent/path"},
        )
        assert resp.status_code == 400

    def test_set_model_path_then_query(self, client):
        client.put(
            "/api/settings/model-path",
            json={"model_path": SAMPLE_MODEL},
        )
        # Should be able to query all endpoints now
        assert client.get("/api/info").status_code == 200
        assert client.get("/api/score").status_code == 200
        assert client.get("/api/check").status_code == 200


# ---- /api/browse ----

class TestBrowseEndpoint:
    def test_browse_default(self, client):
        # Browse the fixtures dir (not home — home can be slow)
        resp = client.get(f"/api/browse?path={FIXTURES}")
        assert resp.status_code == 200
        data = resp.json()
        assert "current" in data
        assert "entries" in data
        assert isinstance(data["entries"], list)

    def test_browse_specific_path(self, client):
        resp = client.get(f"/api/browse?path={FIXTURES}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["current"] == str(FIXTURES)
        names = [e["name"] for e in data["entries"]]
        assert "sample-model" in names

    def test_browse_model_detected(self, client):
        resp = client.get(f"/api/browse?path={FIXTURES}")
        data = resp.json()
        model_entry = next((e for e in data["entries"] if e["name"] == "sample-model"), None)
        assert model_entry is not None
        assert model_entry["is_model"] is True
        assert model_entry["is_dir"] is True

    def test_browse_invalid_path(self, client):
        resp = client.get("/api/browse?path=/nonexistent/path")
        assert resp.status_code == 400


# ---- Static files ----

class TestStaticFiles:
    def test_index_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "DaxOps" in resp.text

    def test_css(self, client):
        resp = client.get("/style.css")
        assert resp.status_code == 200

    def test_js(self, client):
        resp = client.get("/app.js")
        assert resp.status_code == 200


# ---- App factory ----

class TestAppFactory:
    def test_create_app_default(self):
        app = create_app()
        assert app.title == "DaxOps"

    def test_create_app_with_model(self):
        app = create_app(model_path=SAMPLE_MODEL)
        assert app_state.model_path == SAMPLE_MODEL

    def test_app_routes_registered(self):
        app = create_app()
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/api/info" in paths
        assert "/api/score" in paths
        assert "/api/check" in paths
        assert "/api/scan" in paths
        assert "/api/settings" in paths
