"""Tests for Azure DevOps pipeline YAML template."""
from pathlib import Path

import yaml
import pytest

PIPELINE_FILE = Path(__file__).parent.parent / "azure-pipelines-daxops.yml"


@pytest.fixture
def pipeline():
    return yaml.safe_load(PIPELINE_FILE.read_text())


class TestAzurePipelineStructure:
    def test_file_exists(self):
        assert PIPELINE_FILE.exists()

    def test_valid_yaml(self, pipeline):
        assert isinstance(pipeline, dict)

    def test_trigger_paths(self, pipeline):
        paths = pipeline["trigger"]["paths"]["include"]
        assert "**/*.tmdl" in paths
        assert ".daxops.yml" in paths

    def test_pr_trigger(self, pipeline):
        paths = pipeline["pr"]["paths"]["include"]
        assert "**/*.tmdl" in paths

    def test_parameters(self, pipeline):
        params = pipeline["parameters"]
        assert len(params) == 1
        assert params[0]["name"] == "modelPath"
        assert params[0]["type"] == "string"
        assert params[0]["default"] == "."

    def test_python_version(self, pipeline):
        assert pipeline["variables"]["pythonVersion"] == "3.12"

    def test_pool(self, pipeline):
        assert pipeline["pool"]["vmImage"] == "ubuntu-latest"

    def test_steps_count(self, pipeline):
        steps = pipeline["steps"]
        assert len(steps) >= 5

    def test_installs_daxops(self, pipeline):
        scripts = [s.get("script", "") for s in pipeline["steps"]]
        assert any("pip install daxops" in s for s in scripts)

    def test_runs_score(self, pipeline):
        scripts = [s.get("script", "") for s in pipeline["steps"]]
        assert any("daxops score" in s for s in scripts)

    def test_runs_check(self, pipeline):
        scripts = [s.get("script", "") for s in pipeline["steps"]]
        assert any("daxops check" in s for s in scripts)

    def test_publishes_artifacts(self, pipeline):
        tasks = [s.get("task", "") for s in pipeline["steps"]]
        assert any("PublishBuildArtifacts" in t for t in tasks)

    def test_detects_model_path(self, pipeline):
        scripts = [s.get("script", "") for s in pipeline["steps"]]
        assert any("model.tmdl" in s for s in scripts)
