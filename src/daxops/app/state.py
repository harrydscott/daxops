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
        self.ssas_server: str | None = None
        self.ssas_database: str | None = None

    @property
    def connection_mode(self) -> str:
        """Return the current connection mode: 'ssas', 'hybrid', 'tmdl', or 'none'."""
        has_ssas = self.ssas_server is not None and self.ssas_database is not None
        has_tmdl = self.model_path is not None
        if has_ssas and has_tmdl:
            return "hybrid"
        if has_ssas:
            return "ssas"
        if has_tmdl:
            return "tmdl"
        return "none"

    def set_model_path(self, path: str) -> None:
        """Set the model path and load config from that location."""
        self.model_path = path
        self.config = load_config(Path(path))

    def set_ssas(self, server: str, database: str) -> None:
        """Set SSAS connection parameters."""
        self.ssas_server = server
        self.ssas_database = database

    def scan(self) -> SemanticModel:
        """Parse the model from the best available source and cache it.

        In hybrid/ssas mode, reads from SSAS (live model state).
        In tmdl mode, reads from disk.
        """
        mode = self.connection_mode
        if mode in ("ssas", "hybrid"):
            return self._scan_ssas()
        if mode == "tmdl":
            return self._scan_tmdl()
        raise ValueError("No model path or SSAS connection configured")

    def _scan_tmdl(self) -> SemanticModel:
        """Parse model from TMDL files on disk."""
        if not self.model_path:
            raise ValueError("No model path configured")
        from daxops.parser.tmdl import parse_model
        self.model = parse_model(self.model_path)
        return self.model

    def _scan_ssas(self) -> SemanticModel:
        """Scan model from local SSAS instance."""
        if not self.ssas_server or not self.ssas_database:
            raise ValueError("SSAS server and database required")
        from daxops.ssas import scan_ssas
        self.model = scan_ssas(self.ssas_server, self.ssas_database)
        return self.model

    def ensure_model(self) -> SemanticModel:
        """Return cached model or scan if not yet loaded."""
        if self.model is None:
            return self.scan()
        return self.model


app_state = AppState()
