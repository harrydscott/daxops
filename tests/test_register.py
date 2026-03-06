"""Tests for the register-tool CLI command and registration logic."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from daxops.cli import cli
from daxops.register import (
    PBITOOL_FILENAME,
    build_pbitool_json,
    register_tool,
    unregister_tool,
)


class TestBuildPbitoolJson:
    def test_structure(self):
        data = build_pbitool_json()
        assert data["version"] == "1.0"
        assert data["name"] == "DaxOps"
        assert "path" in data
        assert '"%server%"' in data["arguments"]
        assert '"%database%"' in data["arguments"]

    def test_arguments_format(self):
        data = build_pbitool_json()
        assert data["arguments"].startswith("-m daxops app")
        assert "--ssas-server" in data["arguments"]
        assert "--database" in data["arguments"]

    def test_has_icon(self):
        data = build_pbitool_json()
        assert data["iconData"].startswith("data:image/png;base64,")


class TestRegisterTool:
    def test_register_creates_file(self, tmp_path):
        result = register_tool(str(tmp_path))
        assert result == tmp_path / PBITOOL_FILENAME
        assert result.exists()
        data = json.loads(result.read_text())
        assert data["name"] == "DaxOps"

    def test_register_overwrites(self, tmp_path):
        (tmp_path / PBITOOL_FILENAME).write_text("{}")
        result = register_tool(str(tmp_path))
        data = json.loads(result.read_text())
        assert data["name"] == "DaxOps"

    def test_register_creates_parent_dirs(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c"
        result = register_tool(str(deep))
        assert result.exists()

    def test_unregister_removes_file(self, tmp_path):
        register_tool(str(tmp_path))
        result = unregister_tool(str(tmp_path))
        assert result is not None
        assert not (tmp_path / PBITOOL_FILENAME).exists()

    def test_unregister_missing_returns_none(self, tmp_path):
        result = unregister_tool(str(tmp_path))
        assert result is None


class TestRegisterToolCLI:
    def test_register_cli(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli, ["register-tool", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "Registered" in result.output
        assert (tmp_path / PBITOOL_FILENAME).exists()

    def test_register_cli_json_valid(self, tmp_path):
        runner = CliRunner()
        runner.invoke(cli, ["register-tool", "--path", str(tmp_path)])
        data = json.loads((tmp_path / PBITOOL_FILENAME).read_text())
        assert data["version"] == "1.0"

    def test_uninstall_cli(self, tmp_path):
        runner = CliRunner()
        runner.invoke(cli, ["register-tool", "--path", str(tmp_path)])
        result = runner.invoke(cli, ["register-tool", "--uninstall", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "Removed" in result.output
        assert not (tmp_path / PBITOOL_FILENAME).exists()

    def test_uninstall_missing(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli, ["register-tool", "--uninstall", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "not found" in result.output
