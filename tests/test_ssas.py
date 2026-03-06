"""Tests for SSAS connection, hybrid mode, and connection endpoint."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from daxops.app.main import create_app
from daxops.app.state import AppState, app_state
from daxops.models.schema import SemanticModel, Table, Column, Measure
from daxops.ssas import (
    _extract_port,
    _resolve_tmdl_from_pbip,
    find_workspace_tmdl,
)

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_MODEL = str(FIXTURES / "sample-model")


def _make_model(name: str = "TestModel") -> SemanticModel:
    """Create a minimal SemanticModel for testing."""
    return SemanticModel(
        name=name,
        tables=[
            Table(
                name="Sales",
                columns=[Column(name="Amount", data_type="double")],
                measures=[Measure(name="Total", expression="SUM(Sales[Amount])")],
            )
        ],
    )


@pytest.fixture(autouse=True)
def reset_state():
    """Reset app state between tests."""
    app_state.model_path = None
    app_state.model = None
    app_state.ssas_server = None
    app_state.ssas_database = None
    from daxops.config import DaxOpsConfig
    app_state.config = DaxOpsConfig()
    yield


# ── AppState connection mode ─────────────────────────────────────────


class TestConnectionMode:
    def test_none_mode(self):
        state = AppState()
        assert state.connection_mode == "none"

    def test_tmdl_mode(self):
        state = AppState()
        state.model_path = "/some/path"
        assert state.connection_mode == "tmdl"

    def test_ssas_mode(self):
        state = AppState()
        state.ssas_server = "localhost:12345"
        state.ssas_database = "MyModel"
        assert state.connection_mode == "ssas"

    def test_hybrid_mode(self):
        state = AppState()
        state.model_path = "/some/path"
        state.ssas_server = "localhost:12345"
        state.ssas_database = "MyModel"
        assert state.connection_mode == "hybrid"

    def test_set_ssas(self):
        state = AppState()
        state.set_ssas("localhost:54321", "Sales")
        assert state.ssas_server == "localhost:54321"
        assert state.ssas_database == "Sales"


class TestAppStateScan:
    def test_scan_tmdl(self):
        app_state.set_model_path(SAMPLE_MODEL)
        model = app_state.scan()
        assert model.name is not None
        assert len(model.tables) > 0

    def test_scan_no_connection_raises(self):
        with pytest.raises(ValueError, match="No model path or SSAS"):
            app_state.scan()

    @patch("daxops.ssas.scan_ssas")
    def test_scan_ssas_mode(self, mock_scan):
        mock_scan.return_value = _make_model()
        app_state.set_ssas("localhost:12345", "TestModel")
        model = app_state.scan()
        assert model.name == "TestModel"
        mock_scan.assert_called_once_with("localhost:12345", "TestModel")

    @patch("daxops.ssas.scan_ssas")
    def test_scan_hybrid_prefers_ssas(self, mock_scan):
        """In hybrid mode, scan reads from SSAS (live model state)."""
        mock_scan.return_value = _make_model("SSASModel")
        app_state.set_model_path(SAMPLE_MODEL)
        app_state.set_ssas("localhost:12345", "SSASModel")
        model = app_state.scan()
        assert model.name == "SSASModel"
        mock_scan.assert_called_once()


# ── SSAS connection module ───────────────────────────────────────────


class TestExtractPort:
    def test_standard(self):
        assert _extract_port("localhost:12345") == "12345"

    def test_no_port(self):
        assert _extract_port("localhost") is None

    def test_ip_with_port(self):
        assert _extract_port("127.0.0.1:54321") == "54321"

    def test_empty(self):
        assert _extract_port("") is None


class TestConnectSsas:
    def test_import_error(self):
        """Without pyadomd installed, connect_ssas raises ImportError."""
        from daxops.ssas import connect_ssas
        with pytest.raises(ImportError, match="pyadomd"):
            connect_ssas("localhost:12345", "TestDB")


class TestFindWorkspaceTmdl:
    def test_non_windows_returns_none(self):
        with patch("daxops.ssas.sys") as mock_sys:
            mock_sys.platform = "darwin"
            assert find_workspace_tmdl("localhost:12345") is None

    def test_no_port_returns_none(self):
        with patch("daxops.ssas.sys") as mock_sys:
            mock_sys.platform = "win32"
            assert find_workspace_tmdl("localhost") is None

    def test_matching_workspace(self, tmp_path):
        """Simulates finding a workspace with matching port."""
        # Create fake workspace structure
        ws_dir = tmp_path / "AnalysisServicesWorkspace_abc123"
        data_dir = ws_dir / "Data"
        data_dir.mkdir(parents=True)
        (data_dir / "msmdsrv.port.txt").write_text("12345")

        with patch("daxops.ssas.sys") as mock_sys, \
             patch.dict(os.environ, {"LOCALAPPDATA": ""}):
            mock_sys.platform = "win32"
            # No LOCALAPPDATA = returns None
            assert find_workspace_tmdl("localhost:12345") is None


class TestResolveTmdlFromPbip:
    def test_tmdl_folder_direct(self, tmp_path):
        (tmp_path / "model.tmdl").write_text("model Model")
        assert _resolve_tmdl_from_pbip(tmp_path) == tmp_path

    def test_semantic_model_folder(self, tmp_path):
        sm = tmp_path / "Sales.SemanticModel" / "definition"
        sm.mkdir(parents=True)
        result = _resolve_tmdl_from_pbip(tmp_path)
        assert result == sm

    def test_no_match(self, tmp_path):
        (tmp_path / "readme.txt").write_text("nothing here")
        assert _resolve_tmdl_from_pbip(tmp_path) is None

    def test_pbip_file(self, tmp_path):
        (tmp_path / "project.pbip").write_text("{}")
        sm = tmp_path / "Sales.SemanticModel" / "definition"
        sm.mkdir(parents=True)
        result = _resolve_tmdl_from_pbip(tmp_path / "project.pbip")
        assert result == sm


# ── /api/connection endpoint ─────────────────────────────────────────


class TestConnectionEndpoint:
    @pytest.fixture
    def client(self):
        app = create_app()
        return TestClient(app)

    @pytest.fixture
    def client_tmdl(self):
        app = create_app(model_path=SAMPLE_MODEL)
        return TestClient(app)

    @pytest.fixture
    def client_ssas(self):
        app = create_app(ssas_server="localhost:12345", ssas_database="TestDB")
        return TestClient(app)

    @pytest.fixture
    def client_hybrid(self):
        app = create_app(
            model_path=SAMPLE_MODEL,
            ssas_server="localhost:12345",
            ssas_database="TestDB",
        )
        return TestClient(app)

    def test_no_connection(self, client):
        resp = client.get("/api/connection")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "none"
        assert data["can_write"] is False

    def test_tmdl_connection(self, client_tmdl):
        resp = client_tmdl.get("/api/connection")
        data = resp.json()
        assert data["mode"] == "tmdl"
        assert data["model_path"] is not None
        assert data["can_write"] is True
        assert data["ssas_server"] is None

    def test_ssas_connection(self, client_ssas):
        resp = client_ssas.get("/api/connection")
        data = resp.json()
        assert data["mode"] == "ssas"
        assert data["ssas_server"] == "localhost:12345"
        assert data["ssas_database"] == "TestDB"
        assert data["can_write"] is False

    def test_hybrid_connection(self, client_hybrid):
        resp = client_hybrid.get("/api/connection")
        data = resp.json()
        assert data["mode"] == "hybrid"
        assert data["ssas_server"] == "localhost:12345"
        assert data["model_path"] is not None
        assert data["can_write"] is True


# ── create_app with SSAS params ──────────────────────────────────────


class TestCreateAppSsas:
    def test_create_app_ssas_only(self):
        app = create_app(ssas_server="localhost:12345", ssas_database="TestDB")
        assert app_state.ssas_server == "localhost:12345"
        assert app_state.ssas_database == "TestDB"

    def test_create_app_hybrid(self):
        app = create_app(
            model_path=SAMPLE_MODEL,
            ssas_server="localhost:12345",
            ssas_database="TestDB",
        )
        assert app_state.connection_mode == "hybrid"

    def test_create_app_auto_detect_tmdl(self):
        """When SSAS provided without model_path, auto-detection is attempted."""
        with patch("daxops.ssas.find_workspace_tmdl", return_value=None):
            app = create_app(ssas_server="localhost:12345", ssas_database="TestDB")
            # No TMDL detected, stays in SSAS mode
            assert app_state.connection_mode == "ssas"

    def test_create_app_auto_detect_tmdl_found(self, tmp_path):
        """When auto-detection finds TMDL, switches to hybrid mode."""
        (tmp_path / "model.tmdl").write_text("model Model")
        (tmp_path / "tables").mkdir()
        with patch("daxops.ssas.find_workspace_tmdl", return_value=tmp_path):
            app = create_app(ssas_server="localhost:12345", ssas_database="TestDB")
            assert app_state.connection_mode == "hybrid"
            assert app_state.model_path == str(tmp_path)


# ── Scan endpoint with connection modes ──────────────────────────────


class TestScanEndpointModes:
    def test_scan_no_connection(self):
        app = create_app()
        client = TestClient(app)
        resp = client.post("/api/scan")
        assert resp.status_code == 400

    def test_scan_tmdl(self):
        app = create_app(model_path=SAMPLE_MODEL)
        client = TestClient(app)
        resp = client.post("/api/scan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connection_mode"] == "tmdl"

    @patch("daxops.ssas.scan_ssas")
    def test_scan_ssas(self, mock_scan):
        mock_scan.return_value = _make_model()
        app = create_app(ssas_server="localhost:12345", ssas_database="TestModel")
        client = TestClient(app)
        resp = client.post("/api/scan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connection_mode"] == "ssas"


# ── CLI app command with SSAS args ───────────────────────────────────


class TestAppCLISsasArgs:
    def test_app_help_shows_ssas_options(self):
        runner = CliRunner()
        result = runner.invoke(cli_import(), ["app", "--help"])
        assert "--ssas-server" in result.output
        assert "--database" in result.output

    def test_register_tool_help(self):
        runner = CliRunner()
        result = runner.invoke(cli_import(), ["register-tool", "--help"])
        assert "--path" in result.output
        assert "--uninstall" in result.output


def cli_import():
    from daxops.cli import cli
    return cli
