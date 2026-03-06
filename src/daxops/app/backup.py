"""Backup system for TMDL files — create/restore/prune timestamped backups."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

MAX_BACKUPS = 10
BACKUP_DIR_NAME = ".daxops-backup"


def _backup_root(model_path: str | Path) -> Path:
    """Return the backup directory inside the model folder."""
    return Path(model_path) / BACKUP_DIR_NAME


def ensure_gitignore(model_path: str | Path) -> None:
    """Add .daxops-backup/ to .gitignore if not already present."""
    root = Path(model_path)
    # Walk up to find .gitignore (or create in model root)
    gitignore = root / ".gitignore"
    # Also check parent directories for the repo root
    for parent in [root, *root.parents]:
        candidate = parent / ".gitignore"
        if candidate.exists():
            gitignore = candidate
            break
        if (parent / ".git").exists():
            gitignore = candidate
            break

    entry = ".daxops-backup/"
    if gitignore.exists():
        content = gitignore.read_text()
        if entry in content:
            return
        if not content.endswith("\n"):
            content += "\n"
        content += f"{entry}\n"
        gitignore.write_text(content)
    else:
        gitignore.write_text(f"{entry}\n")


def create_backup(model_path: str | Path, files: list[Path]) -> Path | None:
    """Back up the given files into a timestamped subdirectory.

    Returns the backup directory path, or None if no files to back up.
    """
    if not files:
        return None

    root = Path(model_path)
    backup_root = _backup_root(root)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = backup_root / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    for file_path in files:
        if file_path.exists():
            # Preserve relative structure within model folder
            try:
                rel = file_path.relative_to(root)
            except ValueError:
                rel = Path(file_path.name)
            dest = backup_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, dest)

    ensure_gitignore(root)
    _prune_old_backups(root)
    return backup_dir


def restore_latest(model_path: str | Path) -> list[str]:
    """Restore files from the most recent backup.

    Returns a list of restored file paths (relative to model root).
    """
    root = Path(model_path)
    backup_root = _backup_root(root)
    if not backup_root.exists():
        return []

    backups = sorted(backup_root.iterdir())
    backups = [b for b in backups if b.is_dir()]
    if not backups:
        return []

    latest = backups[-1]
    restored: list[str] = []
    for backed_up in latest.rglob("*"):
        if backed_up.is_file():
            rel = backed_up.relative_to(latest)
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backed_up, dest)
            restored.append(str(rel))

    # Remove the used backup
    shutil.rmtree(latest)
    return restored


def list_backups(model_path: str | Path) -> list[dict]:
    """List available backups with timestamp and file count."""
    backup_root = _backup_root(model_path)
    if not backup_root.exists():
        return []

    result = []
    for entry in sorted(backup_root.iterdir(), reverse=True):
        if entry.is_dir():
            files = list(entry.rglob("*"))
            file_count = sum(1 for f in files if f.is_file())
            result.append({
                "timestamp": entry.name,
                "path": str(entry),
                "file_count": file_count,
            })
    return result


def _prune_old_backups(model_path: str | Path) -> None:
    """Remove oldest backups beyond MAX_BACKUPS."""
    backup_root = _backup_root(model_path)
    if not backup_root.exists():
        return

    backups = sorted(b for b in backup_root.iterdir() if b.is_dir())
    while len(backups) > MAX_BACKUPS:
        oldest = backups.pop(0)
        shutil.rmtree(oldest)
