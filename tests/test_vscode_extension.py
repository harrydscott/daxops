"""Tests for VS Code extension stub structure."""
import json
from pathlib import Path

import pytest

EXTENSION_DIR = Path(__file__).parent.parent / "vscode-daxops"


class TestExtensionPackageJson:
    @pytest.fixture
    def pkg(self):
        return json.loads((EXTENSION_DIR / "package.json").read_text())

    def test_package_json_exists(self):
        assert (EXTENSION_DIR / "package.json").exists()

    def test_name(self, pkg):
        assert pkg["name"] == "daxops"

    def test_display_name(self, pkg):
        assert pkg["displayName"] == "DaxOps"

    def test_engines_vscode(self, pkg):
        assert "vscode" in pkg["engines"]

    def test_main_entry_point(self, pkg):
        assert pkg["main"] == "./out/extension.js"

    def test_activation_events(self, pkg):
        events = pkg["activationEvents"]
        assert any("model.tmdl" in e for e in events)
        assert any(".pbip" in e for e in events)

    def test_commands_registered(self, pkg):
        commands = pkg["contributes"]["commands"]
        command_ids = [c["command"] for c in commands]
        assert "daxops.score" in command_ids
        assert "daxops.check" in command_ids
        assert "daxops.fix" in command_ids
        assert "daxops.fixDryRun" in command_ids
        assert "daxops.report" in command_ids
        assert "daxops.watch" in command_ids
        assert "daxops.badge" in command_ids
        assert "daxops.baseline" in command_ids

    def test_configuration_settings(self, pkg):
        props = pkg["contributes"]["configuration"]["properties"]
        assert "daxops.pythonPath" in props
        assert "daxops.modelPath" in props
        assert "daxops.runOnSave" in props

    def test_tmdl_language_registered(self, pkg):
        langs = pkg["contributes"]["languages"]
        tmdl = [l for l in langs if l["id"] == "tmdl"]
        assert len(tmdl) == 1
        assert ".tmdl" in tmdl[0]["extensions"]

    def test_categories(self, pkg):
        assert "Linters" in pkg["categories"]


class TestExtensionFiles:
    def test_extension_ts_exists(self):
        assert (EXTENSION_DIR / "src" / "extension.ts").exists()

    def test_tsconfig_exists(self):
        assert (EXTENSION_DIR / "tsconfig.json").exists()

    def test_readme_exists(self):
        assert (EXTENSION_DIR / "README.md").exists()

    def test_extension_has_activate(self):
        src = (EXTENSION_DIR / "src" / "extension.ts").read_text()
        assert "export function activate" in src

    def test_extension_has_deactivate(self):
        src = (EXTENSION_DIR / "src" / "extension.ts").read_text()
        assert "export function deactivate" in src

    def test_extension_registers_commands(self):
        src = (EXTENSION_DIR / "src" / "extension.ts").read_text()
        assert "registerCommand" in src

    def test_extension_run_on_save(self):
        src = (EXTENSION_DIR / "src" / "extension.ts").read_text()
        assert "onDidSaveTextDocument" in src
