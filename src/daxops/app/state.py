"""In-memory application state for the DaxOps web app."""
from __future__ import annotations

from pathlib import Path

from daxops.config import DaxOpsConfig, load_config
from daxops.models.schema import SemanticModel


class AppState:
    """Singleton holding the current model and scan results."""

    def __init__(self) -> None:
        self.model_path: str | None = None
        self.model: SemanticModel | None = None
        self.config: DaxOpsConfig = DaxOpsConfig()

    def set_model_path(self, path: str) -> None:
        """Set the model path and load config from that location."""
        self.model_path = path
        self.config = load_config(Path(path))

    def scan(self) -> SemanticModel:
        """Parse the model from disk and cache it."""
        if not self.model_path:
            raise ValueError("No model path configured")
        from daxops.parser.tmdl import parse_model
        self.model = parse_model(self.model_path)
        return self.model

    def ensure_model(self) -> SemanticModel:
        """Return cached model or scan if not yet loaded."""
        if self.model is None:
            return self.scan()
        return self.model


app_state = AppState()
