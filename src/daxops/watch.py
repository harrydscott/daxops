"""Watch mode — re-runs score + check on file changes."""
from __future__ import annotations

import time
from pathlib import Path

from rich.console import Console

console = Console()


def _get_file_mtimes(root: Path) -> dict[str, float]:
    """Get modification times for all TMDL files under root."""
    mtimes: dict[str, float] = {}
    if not root.is_dir():
        return mtimes
    for f in root.rglob("*.tmdl"):
        try:
            mtimes[str(f)] = f.stat().st_mtime
        except OSError:
            pass
    # Also watch config files
    for name in (".daxops.yml", ".daxops.yaml", "daxops.yml"):
        cfg = root / name
        if cfg.exists():
            try:
                mtimes[str(cfg)] = cfg.stat().st_mtime
            except OSError:
                pass
    return mtimes


def _run_score_and_check(model_path: str, fmt: str, config) -> None:
    """Run score + check and print results (non-exiting)."""
    from daxops.parser.tmdl import parse_model
    from daxops.scoring import score_bronze, score_silver, score_gold
    from daxops.health.rules import run_health_checks, Severity

    try:
        model = parse_model(model_path)
    except Exception as e:
        console.print(f"[red]Parse error: {e}")
        return

    bronze = score_bronze(model)
    silver = score_silver(model)
    gold = score_gold(model)

    b = sum(c.score for c in bronze)
    s = sum(c.score for c in silver)
    g = sum(c.score for c in gold)

    b_min = config.score.bronze_min
    s_min = config.score.silver_min
    g_min = config.score.gold_min

    if b >= b_min and s >= s_min and g >= g_min:
        tier = "Gold"
    elif b >= b_min and s >= s_min:
        tier = "Silver"
    elif b >= b_min:
        tier = "Bronze"
    else:
        tier = "None"

    findings = run_health_checks(model)
    if config.exclude_rules:
        findings = [f for f in findings if f.rule not in config.exclude_rules]
    if config.exclude_tables:
        findings = [f for f in findings if not any(
            f.object_path.startswith(t) for t in config.exclude_tables
        )]

    errors = sum(1 for f in findings if f.severity == Severity.ERROR)
    warnings = sum(1 for f in findings if f.severity == Severity.WARNING)
    info = sum(1 for f in findings if f.severity == Severity.INFO)

    console.print(
        f"  Score: B={b} S={s} G={g} | Tier: [bold]{tier}[/bold] | "
        f"Findings: {errors}E {warnings}W {info}I"
    )


def watch_model(model_path: str, interval: float = 1.0, fmt: str = "terminal", config=None) -> None:
    """Watch a model directory for changes and re-run score+check."""
    from daxops.parser.tmdl import resolve_model_root

    root = resolve_model_root(model_path)
    console.print(f"[bold]Watching [cyan]{root}[/cyan] for changes (Ctrl+C to stop)...")

    # Initial run
    console.print("[dim]--- initial run ---")
    _run_score_and_check(model_path, fmt, config)

    prev_mtimes = _get_file_mtimes(root)

    try:
        while True:
            time.sleep(interval)
            curr_mtimes = _get_file_mtimes(root)

            if curr_mtimes != prev_mtimes:
                # Find changed files
                changed = []
                for f, mtime in curr_mtimes.items():
                    if f not in prev_mtimes or prev_mtimes[f] != mtime:
                        changed.append(Path(f).name)
                for f in prev_mtimes:
                    if f not in curr_mtimes:
                        changed.append(f"(deleted) {Path(f).name}")

                console.print(f"\n[dim]--- changed: {', '.join(changed)} ---")
                _run_score_and_check(model_path, fmt, config)
                prev_mtimes = curr_mtimes
    except KeyboardInterrupt:
        console.print("\n[dim]Watch stopped.")
