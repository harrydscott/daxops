"""Progress indicators for large model operations."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from rich.console import Console


@contextmanager
def progress_status(
    console: Console,
    message: str,
    enabled: bool = True,
) -> Generator[None, None, None]:
    """Show a spinner status while an operation runs.

    Only shows the spinner when enabled (i.e., terminal output, not JSON).
    """
    if not enabled:
        yield
        return

    with console.status(f"[dim]{message}[/dim]", spinner="dots"):
        yield
