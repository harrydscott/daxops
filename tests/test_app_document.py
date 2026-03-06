"""Tests for AI description editor endpoints and document writer."""
from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from daxops.app.main import create_app
from daxops.app.state import app_state

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_MODEL = str(FIXTURES / "sample-model")


@pytest.fixture(autouse=True)
def reset_state():
    """Reset app state and staged descriptions between tests."""
    app_state.model_path = None
    app_state.model = None
    from daxops.config import DaxOpsConfig
    app_state.config = DaxOpsConfig()
    from daxops.app.routes.document import _reset_staged
    _reset_staged()
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


# ---- AI Settings ----

class TestAISettings:
    def test_get_ai_settings_defaults(self, client):
        resp = client.get("/api/ai/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "openai"
        assert data["llm_model"] == "gpt-4o"
        assert data["has_api_key"] is False

    def test_set_ai_settings(self, client):
        resp = client.put("/api/ai/settings", json={
            "provider": "anthropic",
            "llm_model": "claude-sonnet-4-5-20250514",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "anthropic"
        assert data["llm_model"] == "claude-sonnet-4-5-20250514"

    def test_set_ai_settings_invalid_provider(self, client):
        resp = client.put("/api/ai/settings", json={
            "provider": "invalid",
        })
        assert resp.status_code == 400
        assert "Unsupported" in resp.json()["detail"]

    def test_set_ai_settings_azure(self, client):
        resp = client.put("/api/ai/settings", json={
            "provider": "azure_openai",
            "azure_endpoint": "https://myresource.openai.azure.com",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "azure_openai"
        assert data["azure_endpoint"] == "https://myresource.openai.azure.com"

    @patch("daxops.app.routes.document._get_api_key")
    def test_set_api_key(self, mock_get_key, client):
        mock_get_key.return_value = "sk-test"
        with patch("daxops.document.keystore.store_api_key") as mock_store:
            resp = client.post("/api/ai/key", json={
                "provider": "openai",
                "api_key": "sk-test123",
            })
            assert resp.status_code == 200
            mock_store.assert_called_once_with("openai", "sk-test123")

    @patch("daxops.app.routes.document._get_api_key")
    def test_delete_api_key(self, mock_get_key, client):
        mock_get_key.return_value = None
        with patch("daxops.document.keystore.delete_api_key") as mock_delete:
            resp = client.delete("/api/ai/key/openai")
            assert resp.status_code == 200
            mock_delete.assert_called_once_with("openai")

    @patch("daxops.document.generator.test_connection")
    def test_test_connection_success(self, mock_test, client):
        mock_test.return_value = "Connection successful"
        resp = client.post("/api/ai/test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "Connection successful" in data["message"]

    @patch("daxops.document.generator.test_connection")
    def test_test_connection_failure(self, mock_test, client):
        mock_test.side_effect = Exception("Invalid API key")
        resp = client.post("/api/ai/test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "Invalid API key" in data["message"]


# ---- Undocumented objects ----

class TestUndocumented:
    def test_undocumented_no_model(self, client):
        resp = client.get("/api/document/undocumented")
        assert resp.status_code == 400

    def test_undocumented_with_model(self, client_with_model):
        resp = client_with_model.get("/api/document/undocumented")
        assert resp.status_code == 200
        data = resp.json()
        assert "objects" in data
        assert "total" in data
        assert data["total"] > 0
        # Check structure
        obj = data["objects"][0]
        assert "object_type" in obj
        assert "object_path" in obj
        assert "name" in obj
        assert "status" in obj
        assert obj["status"] == "not_generated"

    def test_undocumented_types(self, client_with_model):
        data = client_with_model.get("/api/document/undocumented").json()
        types = set(o["object_type"] for o in data["objects"])
        # Sample model should have undocumented measures, columns, and tables
        assert len(types) > 0


# ---- Generate descriptions ----

class TestGenerateDescriptions:
    @patch("daxops.document.generator.generate_description")
    def test_generate_all(self, mock_gen, client_with_model):
        from daxops.document.generator import GeneratedDescription
        mock_gen.return_value = GeneratedDescription("measure", "Sales.[YTD Revenue]", "Test description")

        resp = client_with_model.post("/api/document/generate", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] > 0
        assert len(data["generated"]) > 0

    @patch("daxops.document.generator.generate_description")
    def test_generate_selected(self, mock_gen, client_with_model):
        from daxops.document.generator import GeneratedDescription
        mock_gen.return_value = GeneratedDescription("measure", "Sales.[YTD Revenue]", "YTD desc")

        # Get undocumented first
        undoc = client_with_model.get("/api/document/undocumented").json()
        first_path = undoc["objects"][0]["object_path"]

        resp = client_with_model.post("/api/document/generate", json={
            "object_paths": [first_path],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["generated"][0]["object_path"] == first_path
        assert data["generated"][0]["status"] == "generated"

    @patch("daxops.document.generator.generate_description")
    def test_generate_error_handling(self, mock_gen, client_with_model):
        mock_gen.side_effect = Exception("API Error")

        undoc = client_with_model.get("/api/document/undocumented").json()
        first_path = undoc["objects"][0]["object_path"]

        resp = client_with_model.post("/api/document/generate", json={
            "object_paths": [first_path],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["generated"][0]["status"] == "not_generated"
        assert "Error:" in data["generated"][0]["description"]

    def test_generate_no_model(self, client):
        resp = client.post("/api/document/generate", json={})
        assert resp.status_code == 400


# ---- Edit/Update descriptions ----

class TestUpdateDescription:
    @patch("daxops.document.generator.generate_description")
    def test_update_description(self, mock_gen, client_with_model):
        from daxops.document.generator import GeneratedDescription

        undoc = client_with_model.get("/api/document/undocumented").json()
        first_path = undoc["objects"][0]["object_path"]

        mock_gen.return_value = GeneratedDescription(
            undoc["objects"][0]["object_type"], first_path, "Generated desc",
        )
        client_with_model.post("/api/document/generate", json={
            "object_paths": [first_path],
        })

        resp = client_with_model.put("/api/document/description", json={
            "object_path": first_path,
            "description": "Edited description",
            "status": "edited",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] == "Edited description"
        assert data["status"] == "edited"

    def test_update_nonexistent(self, client_with_model):
        resp = client_with_model.put("/api/document/description", json={
            "object_path": "nonexistent",
            "description": "test",
            "status": "edited",
        })
        assert resp.status_code == 404


# ---- Approve descriptions ----

class TestApproveDescriptions:
    @patch("daxops.document.generator.generate_description")
    def test_approve(self, mock_gen, client_with_model):
        from daxops.document.generator import GeneratedDescription

        undoc = client_with_model.get("/api/document/undocumented").json()
        first_path = undoc["objects"][0]["object_path"]

        mock_gen.return_value = GeneratedDescription(
            undoc["objects"][0]["object_type"], first_path, "Test desc",
        )
        client_with_model.post("/api/document/generate", json={
            "object_paths": [first_path],
        })

        resp = client_with_model.post("/api/document/approve", json={
            "object_paths": [first_path],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["status"] == "approved"

    @patch("daxops.document.generator.generate_description")
    def test_bulk_approve(self, mock_gen, client_with_model):
        from daxops.document.generator import GeneratedDescription

        undoc = client_with_model.get("/api/document/undocumented").json()
        paths = [o["object_path"] for o in undoc["objects"][:3]]

        for i, path in enumerate(paths):
            mock_gen.return_value = GeneratedDescription(
                undoc["objects"][i]["object_type"], path, f"Desc {i}",
            )

        client_with_model.post("/api/document/generate", json={
            "object_paths": paths,
        })

        resp = client_with_model.post("/api/document/approve", json={
            "object_paths": paths,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == len(paths)
        assert all(d["status"] == "approved" for d in data)


# ---- Write descriptions ----

class TestWriteDescriptions:
    @patch("daxops.document.generator.generate_description")
    def test_write_approved(self, mock_gen, client_with_tmp_model):
        from daxops.document.generator import GeneratedDescription
        client, tmp_model = client_with_tmp_model

        # Get undocumented
        undoc = client.get("/api/document/undocumented").json()
        # Pick a measure that we know is undocumented
        measure_obj = next(
            (o for o in undoc["objects"] if o["object_type"] == "measure"),
            undoc["objects"][0],
        )
        path = measure_obj["object_path"]

        # Generate
        mock_gen.return_value = GeneratedDescription(
            measure_obj["object_type"], path, "A test description for this object.",
        )
        client.post("/api/document/generate", json={"object_paths": [path]})

        # Approve
        client.post("/api/document/approve", json={"object_paths": [path]})

        # Write
        resp = client.post("/api/document/write", json={"object_paths": [path]})
        assert resp.status_code == 200
        data = resp.json()
        assert data["written"] == 1
        assert len(data["files_modified"]) >= 1
        assert data["backup_path"] is not None
        assert "1 descriptions" in data["message"]

    @patch("daxops.document.generator.generate_description")
    def test_write_creates_backup(self, mock_gen, client_with_tmp_model):
        from daxops.document.generator import GeneratedDescription
        client, tmp_model = client_with_tmp_model

        undoc = client.get("/api/document/undocumented").json()
        obj = undoc["objects"][0]
        path = obj["object_path"]

        mock_gen.return_value = GeneratedDescription(obj["object_type"], path, "Backup test desc.")
        client.post("/api/document/generate", json={"object_paths": [path]})
        client.post("/api/document/approve", json={"object_paths": [path]})
        resp = client.post("/api/document/write", json={"object_paths": [path]})

        data = resp.json()
        backup_path = Path(data["backup_path"])
        assert backup_path.exists()
        assert backup_path.parent.name == ".daxops-backup"

    def test_write_no_approved(self, client_with_tmp_model):
        client, _ = client_with_tmp_model
        resp = client.post("/api/document/write", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["written"] == 0

    def test_write_no_model(self, client):
        resp = client.post("/api/document/write", json={})
        assert resp.status_code == 400

    @patch("daxops.document.generator.generate_description")
    def test_write_updates_staged_status(self, mock_gen, client_with_tmp_model):
        from daxops.document.generator import GeneratedDescription
        client, tmp_model = client_with_tmp_model

        undoc = client.get("/api/document/undocumented").json()
        obj = undoc["objects"][0]
        path = obj["object_path"]

        mock_gen.return_value = GeneratedDescription(obj["object_type"], path, "Status test desc.")
        client.post("/api/document/generate", json={"object_paths": [path]})
        client.post("/api/document/approve", json={"object_paths": [path]})
        client.post("/api/document/write", json={"object_paths": [path]})

        # Check staged items show "written" status
        staged = client.get("/api/document/staged").json()
        written_item = next((s for s in staged if s["object_path"] == path), None)
        assert written_item is not None
        assert written_item["status"] == "written"


# ---- Staged descriptions ----

class TestStagedDescriptions:
    def test_staged_empty(self, client_with_model):
        resp = client_with_model.get("/api/document/staged")
        assert resp.status_code == 200
        assert resp.json() == []

    @patch("daxops.document.generator.generate_description")
    def test_staged_after_generate(self, mock_gen, client_with_model):
        from daxops.document.generator import GeneratedDescription

        undoc = client_with_model.get("/api/document/undocumented").json()
        path = undoc["objects"][0]["object_path"]
        mock_gen.return_value = GeneratedDescription(
            undoc["objects"][0]["object_type"], path, "Staged test desc.",
        )
        client_with_model.post("/api/document/generate", json={"object_paths": [path]})

        resp = client_with_model.get("/api/document/staged")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["object_path"] == path


# ---- Document writer ----

class TestDocumentWriter:
    def test_write_measure_description(self, tmp_model):
        from daxops.document.writer import write_descriptions
        files = write_descriptions(str(tmp_model), [{
            "object_type": "measure",
            "object_path": "Sales.[YTD Revenue]",
            "description": "Year-to-date total revenue.",
        }])
        assert len(files) == 1
        content = Path(files[0]).read_text(encoding="utf-8")
        assert "/// Year-to-date total revenue." in content

    def test_write_column_description(self, tmp_model):
        from daxops.document.writer import write_descriptions
        files = write_descriptions(str(tmp_model), [{
            "object_type": "column",
            "object_path": "Sales.Net Amount",
            "description": "Revenue amount after discounts.",
        }])
        assert len(files) == 1
        content = Path(files[0]).read_text(encoding="utf-8")
        assert "/// Revenue amount after discounts." in content

    def test_write_table_description(self, tmp_model):
        from daxops.document.writer import write_descriptions
        # Use a table that doesn't already have a description
        from daxops.parser.tmdl import parse_model
        model = parse_model(str(tmp_model))
        undesc_table = next((t for t in model.tables if not t.description), None)
        if undesc_table is None:
            pytest.skip("All tables already described")

        files = write_descriptions(str(tmp_model), [{
            "object_type": "table",
            "object_path": undesc_table.name,
            "description": "Test table description.",
        }])
        assert len(files) >= 1
        content = Path(files[0]).read_text(encoding="utf-8")
        assert "/// Test table description." in content

    def test_write_does_not_duplicate_description(self, tmp_model):
        from daxops.document.writer import write_descriptions
        # Total Revenue already has a description in sample-model
        files = write_descriptions(str(tmp_model), [{
            "object_type": "measure",
            "object_path": "Sales.[Total Revenue]",
            "description": "Duplicate desc.",
        }])
        # Should not write — Total Revenue already has a /// description
        content = (tmp_model / "tables" / "Sales.tmdl").read_text(encoding="utf-8")
        assert "Duplicate desc." not in content

    def test_write_multiple_descriptions(self, tmp_model):
        from daxops.document.writer import write_descriptions
        files = write_descriptions(str(tmp_model), [
            {
                "object_type": "measure",
                "object_path": "Sales.[YTD Revenue]",
                "description": "Year-to-date total revenue.",
            },
            {
                "object_type": "measure",
                "object_path": "Sales.[Revenue LY]",
                "description": "Total revenue from last year.",
            },
        ])
        assert len(files) == 1  # Both in Sales.tmdl
        content = Path(files[0]).read_text(encoding="utf-8")
        assert "/// Year-to-date total revenue." in content
        assert "/// Total revenue from last year." in content


# ---- Generator unit tests ----

class TestGenerator:
    def test_find_undocumented(self):
        from daxops.document.generator import find_undocumented
        from daxops.parser.tmdl import parse_model
        model = parse_model(SAMPLE_MODEL)
        undoc = find_undocumented(model)
        assert len(undoc) > 0
        types = set(o.object_type for o in undoc)
        assert "measure" in types or "column" in types or "table" in types

    def test_build_prompt_measure(self):
        from daxops.document.generator import _build_prompt, UndocumentedObject
        obj = UndocumentedObject(
            object_type="measure",
            object_path="Sales.[Total]",
            name="Total",
            table_name="Sales",
            expression="SUM(Sales[Amount])",
            format_string="#,##0",
        )
        prompt = _build_prompt(obj)
        assert "Total" in prompt
        assert "SUM(Sales[Amount])" in prompt

    def test_build_prompt_column(self):
        from daxops.document.generator import _build_prompt, UndocumentedObject
        obj = UndocumentedObject(
            object_type="column",
            object_path="Sales.Amount",
            name="Amount",
            table_name="Sales",
            data_type="decimal",
        )
        prompt = _build_prompt(obj)
        assert "Amount" in prompt
        assert "decimal" in prompt

    def test_build_prompt_table(self):
        from daxops.document.generator import _build_prompt, UndocumentedObject
        obj = UndocumentedObject(
            object_type="table",
            object_path="Sales",
            name="Sales",
            table_name="Sales",
            columns_hint="Amount, Date",
            measures_hint="Total",
        )
        prompt = _build_prompt(obj)
        assert "Sales" in prompt
        assert "Amount, Date" in prompt


# ---- Keystore ----

class TestKeystore:
    @patch("daxops.document.keystore._keyring")
    def test_store_and_get(self, mock_kr_fn):
        mock_kr = MagicMock()
        mock_kr_fn.return_value = mock_kr

        from daxops.document.keystore import store_api_key, get_api_key
        store_api_key("openai", "sk-test")
        mock_kr.set_password.assert_called_once_with("daxops", "openai", "sk-test")

        mock_kr.get_password.return_value = "sk-test"
        result = get_api_key("openai")
        assert result == "sk-test"

    @patch("daxops.document.keystore._keyring")
    def test_delete(self, mock_kr_fn):
        mock_kr = MagicMock()
        mock_kr_fn.return_value = mock_kr

        from daxops.document.keystore import delete_api_key
        delete_api_key("openai")
        mock_kr.delete_password.assert_called_once_with("daxops", "openai")


# ---- App routes registration ----

class TestAppRoutes:
    def test_document_routes_registered(self):
        app = create_app()
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/api/ai/settings" in paths
        assert "/api/document/generate" in paths
        assert "/api/document/write" in paths
        assert "/api/document/undocumented" in paths
        assert "/api/document/staged" in paths
        assert "/api/document/approve" in paths
        assert "/api/document/description" in paths
        assert "/api/ai/test" in paths
        assert "/api/ai/key" in paths

    def test_websocket_route_registered(self):
        app = create_app()
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/ws/progress" in paths
