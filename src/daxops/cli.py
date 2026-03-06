"""Click-based CLI for DaxOps."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table as RichTable

from daxops import __version__
from daxops.config import DaxOpsConfig, load_config
from daxops.progress import progress_status

console = Console()


class DaxOpsGroup(click.Group):
    def invoke(self, ctx):
        try:
            return super().invoke(ctx)
        except SystemExit:
            raise
        except Exception as e:
            console.print(f"[red]Error: {e}")
            sys.exit(2)


@click.group(cls=DaxOpsGroup)
@click.version_option(__version__)
@click.option("--config", "config_path", type=click.Path(exists=True), default=None, help="Path to .daxops.yml config file")
@click.pass_context
def cli(ctx, config_path: str | None):
    """DaxOps — Semantic Model Lifecycle Tool for Power BI / Microsoft Fabric."""
    ctx.ensure_object(dict)
    if config_path:
        ctx.obj["config"] = load_config(Path(config_path))
    else:
        ctx.obj["config"] = None  # lazy-load per command using model_path


def _get_config(ctx: click.Context, model_path: str | None = None) -> DaxOpsConfig:
    """Get config from context or load from model path."""
    if ctx.obj.get("config"):
        return ctx.obj["config"]
    start = Path(model_path) if model_path else None
    return load_config(start)


@cli.command()
@click.argument("model_path", type=click.Path(exists=True))
@click.option("--format", "fmt", type=click.Choice(["terminal", "json", "markdown"]), default="terminal")
@click.pass_context
def score(ctx, model_path: str, fmt: str):
    """Score a model's AI readiness (Bronze/Silver/Gold)."""
    from daxops.parser.tmdl import parse_model
    from daxops.scoring import score_bronze, score_silver, score_gold
    from daxops.report.markdown import generate_score_report

    config = _get_config(ctx, model_path)
    show_progress = fmt == "terminal"
    with progress_status(console, "Parsing model...", enabled=show_progress):
        model = parse_model(model_path)
    with progress_status(console, "Scoring model...", enabled=show_progress):
        bronze = score_bronze(model)
        silver = score_silver(model)
        gold = score_gold(model)

    b = sum(c.score for c in bronze)
    s = sum(c.score for c in silver)
    g = sum(c.score for c in gold)

    bronze_pass = b >= config.score.bronze_min
    silver_pass = bronze_pass and s >= config.score.silver_min
    gold_pass = silver_pass and g >= config.score.gold_min

    summary = {
        "bronze_score": b, "silver_score": s, "gold_score": g,
        "bronze_pass": bronze_pass, "silver_pass": silver_pass, "gold_pass": gold_pass,
        "thresholds": {
            "bronze_min": config.score.bronze_min,
            "silver_min": config.score.silver_min,
            "gold_min": config.score.gold_min,
        },
    }

    if fmt == "json":
        data = {
            tier: [{"name": c.name, "score": c.score, "max": c.max_score, "details": c.details}
                   for c in criteria]
            for tier, criteria in [("bronze", bronze), ("silver", silver), ("gold", gold)]
        }
        data["summary"] = summary
        click.echo(json.dumps(data, indent=2))
    elif fmt == "markdown":
        click.echo(generate_score_report(bronze, silver, gold))
    else:
        _render_score_terminal(bronze, silver, gold, config)

    # Exit 1 if bronze threshold not met (findings)
    if not bronze_pass:
        sys.exit(1)


def _render_score_terminal(bronze, silver, gold, config=None):
    for tier_name, criteria, color in [("Bronze", bronze, "yellow"), ("Silver", silver, "white"), ("Gold", gold, "bright_yellow")]:
        total = sum(c.score for c in criteria)
        max_total = sum(c.max_score for c in criteria)
        console.print(f"\n[bold {color}]{'━' * 50}")
        console.print(f"[bold {color}]  {tier_name} — {total}/{max_total}")
        console.print(f"[bold {color}]{'━' * 50}")

        for c in criteria:
            icon = "✅" if c.score == 2 else "⚠️ " if c.score == 1 else "❌"
            console.print(f"  {icon} {c.name} [{c.score}/{c.max_score}]")
            for d in c.details:
                console.print(f"      [dim]{d}[/dim]")

    b = sum(c.score for c in bronze)
    s = sum(c.score for c in silver)
    g = sum(c.score for c in gold)

    if config:
        b_min, s_min, g_min = config.score.bronze_min, config.score.silver_min, config.score.gold_min
    else:
        b_min, s_min, g_min = 10, 10, 8

    console.print()
    if b >= b_min and s >= s_min and g >= g_min:
        console.print("[bold bright_yellow]🥇 Gold tier achieved!")
    elif b >= b_min and s >= s_min:
        console.print("[bold white]🥈 Silver tier achieved!")
    elif b >= b_min:
        console.print("[bold yellow]🥉 Bronze tier achieved!")
    else:
        console.print(f"[dim]⬜ No tier achieved (Bronze needs {b_min - b} more points)[/dim]")


@cli.command()
@click.argument("model_path", type=click.Path(exists=True))
@click.option("--format", "fmt", type=click.Choice(["terminal", "json", "markdown"]), default="terminal")
@click.option("--severity", type=click.Choice(["ERROR", "WARNING", "INFO"]), default=None, help="Minimum severity to show")
@click.option("--baseline/--no-baseline", "use_baseline", default=True, help="Apply baseline suppression if available")
@click.pass_context
def check(ctx, model_path: str, fmt: str, severity: str | None, use_baseline: bool):
    """Run health checks on a TMDL model."""
    from daxops.parser.tmdl import parse_model
    from daxops.health.rules import run_health_checks, Severity
    from daxops.report.markdown import generate_health_report
    from daxops.baseline import load_baseline, filter_new_findings

    config = _get_config(ctx, model_path)
    show_progress = fmt == "terminal"
    with progress_status(console, "Parsing model...", enabled=show_progress):
        model = parse_model(model_path)
    with progress_status(console, "Running health checks...", enabled=show_progress):
        findings = run_health_checks(model)

    # Apply config exclude_rules
    if config.exclude_rules:
        findings = [f for f in findings if f.rule not in config.exclude_rules]

    # Apply config exclude_tables
    if config.exclude_tables:
        findings = [f for f in findings if not any(
            f.object_path.startswith(t) for t in config.exclude_tables
        )]

    # Apply baseline suppression
    suppressed_count = 0
    if use_baseline:
        baseline_keys = load_baseline(model_path)
        if baseline_keys:
            all_count = len(findings)
            findings = filter_new_findings(findings, baseline_keys)
            suppressed_count = all_count - len(findings)

    # Use severity from flag or config
    effective_severity = severity or config.severity
    if effective_severity:
        sev_order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
        threshold = sev_order[effective_severity]
        findings = [f for f in findings if sev_order[f.severity.value] <= threshold]

    if fmt == "json":
        data = {
            "findings": [
                {"rule": f.rule, "severity": f.severity.value, "message": f.message,
                 "object": f.object_path, "recommendation": f.recommendation}
                for f in findings
            ],
            "summary": {
                "total": len(findings),
                "errors": sum(1 for f in findings if f.severity == Severity.ERROR),
                "warnings": sum(1 for f in findings if f.severity == Severity.WARNING),
                "info": sum(1 for f in findings if f.severity == Severity.INFO),
                "suppressed": suppressed_count,
            },
        }
        click.echo(json.dumps(data, indent=2))
    elif fmt == "markdown":
        click.echo(generate_health_report(findings))
    else:
        # Summary dashboard
        error_ct = sum(1 for f in findings if f.severity == Severity.ERROR)
        warn_ct = sum(1 for f in findings if f.severity == Severity.WARNING)
        info_ct = sum(1 for f in findings if f.severity == Severity.INFO)

        console.print()
        console.print("[bold]Health Check Summary")
        console.print("━" * 40)
        console.print(f"  [red bold]{error_ct}[/red bold] errors  [yellow bold]{warn_ct}[/yellow bold] warnings  [blue bold]{info_ct}[/blue bold] info")
        if suppressed_count:
            console.print(f"  [dim]{suppressed_count} baseline findings suppressed[/dim]")
        console.print("━" * 40)

        if not findings:
            console.print("\n[green bold]No issues found!")
        else:
            sev_colors = {"ERROR": "red", "WARNING": "yellow", "INFO": "blue"}
            sev_icons = {"ERROR": "X", "WARNING": "!", "INFO": "i"}
            table = RichTable(title=f"{len(findings)} Findings")
            table.add_column("", width=3)
            table.add_column("Severity", style="bold")
            table.add_column("Rule")
            table.add_column("Object", style="dim")
            table.add_column("Message")
            for f in findings:
                color = sev_colors.get(f.severity.value, "white")
                icon = sev_icons.get(f.severity.value, " ")
                table.add_row(
                    f"[{color} bold]{icon}[/{color} bold]",
                    f"[{color}]{f.severity.value}[/{color}]",
                    f.rule,
                    f.object_path,
                    f.message,
                )
            console.print(table)

            # Show recommendations for top findings
            recs = [f for f in findings if f.recommendation]
            if recs:
                console.print("\n[bold]Recommendations:")
                shown = set()
                for f in recs:
                    # Deduplicate by rule+recommendation
                    key = f"{f.rule}:{f.recommendation}"
                    if key not in shown:
                        shown.add(key)
                        color = sev_colors.get(f.severity.value, "white")
                        console.print(f"  [{color}]{f.rule}[/{color}]: {f.recommendation}")

    # Exit code logic: check against config thresholds
    error_count = sum(1 for f in findings if f.severity == Severity.ERROR)
    warning_count = sum(1 for f in findings if f.severity == Severity.WARNING)

    if config.check.max_errors is not None and error_count > config.check.max_errors:
        sys.exit(1)
    elif config.check.max_warnings is not None and warning_count > config.check.max_warnings:
        sys.exit(1)
    elif findings:
        sys.exit(1)


@cli.command()
@click.argument("old_path", type=click.Path(exists=True))
@click.argument("new_path", type=click.Path(exists=True))
@click.option("--format", "fmt", type=click.Choice(["terminal", "json"]), default="terminal")
def diff(old_path: str, new_path: str, fmt: str):
    """Diff two TMDL model versions."""
    from daxops.parser.tmdl import parse_model
    from daxops.diff.semantic import diff_models

    old = parse_model(old_path)
    new = parse_model(new_path)
    result = diff_models(old, new)

    if fmt == "json":
        data = {
            "has_changes": result.has_changes,
            "changes": [
                {"category": c.category, "type": c.change_type, "path": c.path, "details": c.details}
                for c in result.changes
            ],
        }
        click.echo(json.dumps(data, indent=2))
    else:
        if not result.has_changes:
            console.print("[green]No changes detected.")
            return

        type_colors = {"added": "green", "removed": "red", "modified": "yellow"}
        type_icons = {"added": "+", "removed": "-", "modified": "~"}
        for c in result.changes:
            color = type_colors.get(c.change_type, "white")
            icon = type_icons.get(c.change_type, " ")
            detail = f" ({c.details})" if c.details else ""
            console.print(f"  [{color}]{icon} [{c.category}] {c.path}{detail}")

    # Exit 0 for no changes, 1 for changes (useful in CI)
    if result.has_changes:
        sys.exit(1)


@cli.command()
@click.argument("model_path", type=click.Path(exists=True))
@click.option("--format", "fmt", type=click.Choice(["html", "markdown", "json"]), default="html")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output file path")
@click.pass_context
def report(ctx, model_path: str, fmt: str, output: str | None):
    """Generate a full report (score + health checks)."""
    from daxops.parser.tmdl import parse_model
    from daxops.scoring import score_bronze, score_silver, score_gold
    from daxops.health.rules import run_health_checks, Severity
    from daxops.report.markdown import generate_score_report, generate_health_report
    from daxops.report.html import generate_html_report

    config = _get_config(ctx, model_path)
    with progress_status(console, "Parsing model...", enabled=fmt != "json"):
        model = parse_model(model_path)
    with progress_status(console, "Scoring and checking model...", enabled=fmt != "json"):
        bronze = score_bronze(model)
        silver = score_silver(model)
        gold = score_gold(model)
        findings = run_health_checks(model)

    if fmt == "json":
        b = sum(c.score for c in bronze)
        s = sum(c.score for c in silver)
        g = sum(c.score for c in gold)
        data = {
            "scoring": {
                tier: [{"name": c.name, "score": c.score, "max": c.max_score, "details": c.details}
                       for c in criteria]
                for tier, criteria in [("bronze", bronze), ("silver", silver), ("gold", gold)]
            },
            "summary": {
                "bronze_score": b, "silver_score": s, "gold_score": g,
                "bronze_pass": b >= config.score.bronze_min,
                "silver_pass": b >= config.score.bronze_min and s >= config.score.silver_min,
                "gold_pass": b >= config.score.bronze_min and s >= config.score.silver_min and g >= config.score.gold_min,
            },
            "health": {
                "findings": [
                    {"rule": f.rule, "severity": f.severity.value, "message": f.message, "object": f.object_path}
                    for f in findings
                ],
                "total": len(findings),
                "errors": sum(1 for f in findings if f.severity == Severity.ERROR),
                "warnings": sum(1 for f in findings if f.severity == Severity.WARNING),
                "info": sum(1 for f in findings if f.severity == Severity.INFO),
            },
        }
        content = json.dumps(data, indent=2)
        if output:
            Path(output).write_text(content, encoding="utf-8")
            console.print(f"[green]Report written to {output}")
        else:
            click.echo(content)
        return

    if fmt == "html":
        content = generate_html_report(bronze, silver, gold, findings)
        ext = ".html"
    else:
        content = generate_score_report(bronze, silver, gold) + "\n\n" + generate_health_report(findings)
        ext = ".md"

    if output:
        out_path = Path(output)
    else:
        out_path = Path(f"daxops-report{ext}")

    out_path.write_text(content, encoding="utf-8")
    console.print(f"[green]Report written to {out_path}")


@cli.command()
@click.argument("model_path", type=click.Path(exists=True))
@click.option("--format", "fmt", type=click.Choice(["terminal", "json"]), default="terminal")
@click.option("--provider", type=click.Choice(["openai"]), default="openai")
@click.option("--model", "llm_model", default="gpt-4o")
@click.option("--api-key", envvar="OPENAI_API_KEY", default=None)
@click.option("--dry-run", is_flag=True, help="Show what would be documented without calling LLM")
def document(model_path: str, fmt: str, provider: str, llm_model: str, api_key: str | None, dry_run: bool):
    """Auto-generate descriptions for undocumented objects using LLM."""
    from daxops.parser.tmdl import parse_model

    model = parse_model(model_path)

    # Find undocumented objects
    undoc = []
    for t in model.tables:
        if not t.description:
            undoc.append({"type": "table", "path": t.name})
        for m in t.measures:
            if not m.description:
                undoc.append({"type": "measure", "path": f"{t.name}.[{m.name}]"})
        for c in t.columns:
            if not c.description and not c.is_hidden:
                undoc.append({"type": "column", "path": f"{t.name}.{c.name}"})

    if not undoc:
        if fmt == "json":
            click.echo(json.dumps({"undocumented": [], "generated": []}, indent=2))
        else:
            console.print("[green]All objects are documented! Nothing to do.")
        return

    if fmt == "json" and dry_run:
        click.echo(json.dumps({"undocumented": undoc, "generated": []}, indent=2))
        return

    if fmt != "json":
        console.print(f"Found {len(undoc)} undocumented objects:")
        for u in undoc:
            console.print(f"  [dim][{u['type']}] {u['path']}[/dim]")

    if dry_run:
        console.print("\n[yellow]Dry run — no LLM calls made.")
        return

    from daxops.document.generator import generate_descriptions
    results = generate_descriptions(model, provider, llm_model, api_key)

    if fmt == "json":
        data = {
            "undocumented": undoc,
            "generated": [{"path": r.object_path, "description": r.description} for r in results],
        }
        click.echo(json.dumps(data, indent=2))
    else:
        console.print(f"\n[green]Generated {len(results)} descriptions:")
        for r in results:
            console.print(f"\n  [bold]{r.object_path}[/bold]")
            console.print(f"  [dim]/// {r.description}[/dim]")


@cli.command()
@click.argument("output_path", type=click.Path())
def init(output_path: str):
    """Initialize a sample TMDL model for testing."""
    import shutil
    sample_dir = Path(__file__).parent.parent.parent / "samples" / "contoso-sales"

    if not sample_dir.exists():
        # Fallback: try relative to package
        import daxops
        pkg_root = Path(daxops.__file__).parent.parent.parent
        sample_dir = pkg_root / "samples" / "contoso-sales"

    if not sample_dir.exists():
        console.print("[red]Sample model not found. Creating minimal model...")
        out = Path(output_path)
        out.mkdir(parents=True, exist_ok=True)
        (out / "tables").mkdir(exist_ok=True)
        (out / "model.tmdl").write_text("model Model\n\tculture: en-GB\n")
        console.print(f"[green]Created minimal model at {out}")
        return

    out = Path(output_path)
    if out.exists():
        console.print(f"[red]{out} already exists. Remove it first.")
        sys.exit(1)
    shutil.copytree(sample_dir, out)
    console.print(f"[green]Sample model created at {out}")


@cli.command()
@click.argument("model_path", type=click.Path(exists=True))
@click.option("--interval", type=float, default=1.0, help="Polling interval in seconds")
@click.option("--format", "fmt", type=click.Choice(["terminal", "json"]), default="terminal")
@click.pass_context
def watch(ctx, model_path: str, interval: float, fmt: str):
    """Watch a model directory and re-run score+check on file changes."""
    from daxops.watch import watch_model

    config = _get_config(ctx, model_path)
    watch_model(model_path, interval=interval, fmt=fmt, config=config)


@cli.command()
@click.argument("model_path", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Show what would be fixed without making changes")
@click.option("--format", "fmt", type=click.Choice(["terminal", "json"]), default="terminal")
def fix(model_path: str, dry_run: bool, fmt: str):
    """Auto-fix common issues (rename dim/fact prefixes, hide keys)."""
    from daxops.fix import run_fixes

    results = run_fixes(model_path, dry_run=dry_run)

    if fmt == "json":
        data = {
            "dry_run": dry_run,
            "fixes": [
                {"rule": r.rule, "file": r.file_path, "description": r.description, "applied": r.applied}
                for r in results
            ],
            "total": len(results),
        }
        click.echo(json.dumps(data, indent=2))
    else:
        if not results:
            console.print("[green]No fixes needed — model looks good!")
            return

        action = "Would apply" if dry_run else "Applied"
        console.print(f"\n[bold]{action} {len(results)} fix(es):\n")
        for r in results:
            icon = "~" if r.applied else " "
            console.print(f"  [{icon}] [bold]{r.rule}[/bold] — {r.description}")
            console.print(f"      [dim]{r.file_path}[/dim]")

        if dry_run:
            console.print("\n[yellow]Dry run — no changes written. Remove --dry-run to apply.")


@cli.command()
@click.argument("model_path", type=click.Path(exists=True))
@click.option("--format", "fmt", type=click.Choice(["terminal", "json"]), default="terminal")
@click.pass_context
def baseline(ctx, model_path: str, fmt: str):
    """Save current findings as a baseline — future runs only show new issues."""
    from daxops.parser.tmdl import parse_model
    from daxops.health.rules import run_health_checks, Severity
    from daxops.baseline import save_baseline

    config = _get_config(ctx, model_path)
    model = parse_model(model_path)
    findings = run_health_checks(model)

    # Apply config excludes
    if config.exclude_rules:
        findings = [f for f in findings if f.rule not in config.exclude_rules]
    if config.exclude_tables:
        findings = [f for f in findings if not any(
            f.object_path.startswith(t) for t in config.exclude_tables
        )]

    baseline_path = save_baseline(findings, model_path)

    if fmt == "json":
        data = {
            "baseline_file": str(baseline_path),
            "suppressed_count": len(findings),
            "findings": [
                {"rule": f.rule, "severity": f.severity.value, "object": f.object_path}
                for f in findings
            ],
        }
        click.echo(json.dumps(data, indent=2))
    else:
        console.print(f"[green]Baseline saved to {baseline_path}")
        console.print(f"[dim]Suppressed {len(findings)} existing findings.")


@cli.command(name="test")
@click.argument("model_path", type=click.Path(exists=True))
@click.argument("test_file", type=click.Path(exists=True))
@click.option("--reference", type=click.Path(exists=True), default=None, help="Reference data file (JSON/YAML) for value comparison")
@click.option("--format", "fmt", type=click.Choice(["terminal", "json"]), default="terminal")
def test_cmd(model_path: str, test_file: str, reference: str | None, fmt: str):
    """Run measure tests against a model."""
    from daxops.parser.tmdl import parse_model
    from daxops.testing import (
        load_test_cases,
        run_static_tests,
        run_tests_with_reference,
        load_reference_data,
        TestStatus,
    )

    model = parse_model(model_path)
    cases = load_test_cases(Path(test_file))

    if reference:
        ref_data = load_reference_data(Path(reference))
        results = run_tests_with_reference(model, cases, ref_data)
    else:
        results = run_static_tests(model, cases)

    passed = sum(1 for r in results if r.status == TestStatus.PASS)
    failed = sum(1 for r in results if r.status == TestStatus.FAIL)
    errors = sum(1 for r in results if r.status == TestStatus.ERROR)

    if fmt == "json":
        data = {
            "results": [
                {
                    "measure": r.test.measure,
                    "status": r.status.value,
                    "expected": r.test.expected,
                    "actual": r.actual,
                    "message": r.message,
                    "description": r.test.description,
                }
                for r in results
            ],
            "summary": {
                "total": len(results),
                "passed": passed,
                "failed": failed,
                "errors": errors,
            },
        }
        click.echo(json.dumps(data, indent=2))
    else:
        status_icons = {TestStatus.PASS: "[green]PASS", TestStatus.FAIL: "[red]FAIL", TestStatus.ERROR: "[yellow]ERROR"}
        for r in results:
            icon = status_icons[r.status]
            desc = f" — {r.test.description}" if r.test.description else ""
            console.print(f"  {icon}[/] {r.test.measure}{desc}")
            if r.message:
                console.print(f"        [dim]{r.message}[/dim]")

        console.print()
        console.print(f"  [bold]{len(results)} tests: [green]{passed} passed[/green], [red]{failed} failed[/red], [yellow]{errors} errors[/yellow]")

    if failed > 0 or errors > 0:
        sys.exit(1)


@cli.command()
@click.argument("model_path", type=click.Path(exists=True))
@click.argument("rules_file", type=click.Path(exists=True))
@click.option("--format", "fmt", type=click.Choice(["terminal", "json"]), default="terminal")
def bpa(model_path: str, rules_file: str, fmt: str):
    """Run Tabular Editor Best Practice Analyzer rules against a model."""
    from daxops.parser.tmdl import parse_model
    from daxops.bpa import load_bpa_rules, run_bpa_checks, get_supported_rule_ids

    show_progress = fmt == "terminal"
    with progress_status(console, "Parsing model...", enabled=show_progress):
        model = parse_model(model_path)
    with progress_status(console, "Running BPA checks...", enabled=show_progress):
        rules = load_bpa_rules(Path(rules_file))
        findings, unmapped = run_bpa_checks(model, rules)

    if fmt == "json":
        data = {
            "findings": [
                {"rule": f.rule, "severity": f.severity.value, "message": f.message, "object": f.object_path}
                for f in findings
            ],
            "summary": {
                "total": len(findings),
                "rules_loaded": len(rules),
                "rules_mapped": len(rules) - len(unmapped),
                "rules_unmapped": len(unmapped),
            },
            "unmapped_rules": [
                {"id": r.id, "name": r.name, "category": r.category}
                for r in unmapped
            ],
            "supported_rules": get_supported_rule_ids(),
        }
        click.echo(json.dumps(data, indent=2))
    else:
        console.print(f"[bold]Loaded {len(rules)} BPA rules ({len(rules) - len(unmapped)} mapped, {len(unmapped)} unmapped)\n")

        if findings:
            sev_colors = {"ERROR": "red", "WARNING": "yellow", "INFO": "blue"}
            from rich.table import Table as RichTable
            table = RichTable(title=f"BPA Findings — {len(findings)} issues")
            table.add_column("Severity", style="bold")
            table.add_column("Rule")
            table.add_column("Object", style="dim")
            table.add_column("Message")
            for f in findings:
                table.add_row(
                    f"[{sev_colors.get(f.severity.value, 'white')}]{f.severity.value}",
                    f.rule,
                    f.object_path,
                    f.message,
                )
            console.print(table)
        else:
            console.print("[green]No BPA findings!")

        if unmapped:
            console.print(f"\n[dim]{len(unmapped)} rules could not be evaluated (require Dynamic LINQ):[/dim]")
            for r in unmapped[:5]:
                console.print(f"  [dim]- {r.id}: {r.name}[/dim]")
            if len(unmapped) > 5:
                console.print(f"  [dim]... and {len(unmapped) - 5} more[/dim]")

    if findings:
        sys.exit(1)


@cli.command()
@click.argument("model_path", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), default=None, help="Output SVG file path")
@click.option("--style", type=click.Choice(["tier", "score"]), default="tier", help="Badge style")
@click.option("--format", "fmt", type=click.Choice(["svg", "json"]), default="svg")
@click.pass_context
def badge(ctx, model_path: str, output: str | None, style: str, fmt: str):
    """Generate an SVG badge showing model tier status."""
    from daxops.parser.tmdl import parse_model
    from daxops.scoring import score_bronze, score_silver, score_gold
    from daxops.badge import determine_tier, generate_tier_badge, generate_score_badge

    config = _get_config(ctx, model_path)
    model = parse_model(model_path)
    b = sum(c.score for c in score_bronze(model))
    s = sum(c.score for c in score_silver(model))
    g = sum(c.score for c in score_gold(model))
    tier = determine_tier(b, s, g, config)

    if fmt == "json":
        data = {"tier": tier, "bronze": b, "silver": s, "gold": g}
        click.echo(json.dumps(data, indent=2))
        return

    if style == "score":
        svg = generate_score_badge(tier, b, s, g)
    else:
        svg = generate_tier_badge(tier)

    if output:
        Path(output).write_text(svg, encoding="utf-8")
        console.print(f"[green]Badge written to {output}")
    else:
        click.echo(svg)


@cli.command()
@click.argument("workspace")
@click.argument("dataset")
@click.option("--connection-string", default=None, help="Full XMLA connection string (overrides workspace/dataset)")
@click.option("--tenant-id", envvar="AZURE_TENANT_ID", default="", help="Azure AD tenant ID")
@click.option("--client-id", envvar="AZURE_CLIENT_ID", default="", help="Azure AD client/app ID")
@click.option("--client-secret", envvar="AZURE_CLIENT_SECRET", default="", help="Azure AD client secret")
@click.option("--format", "fmt", type=click.Choice(["terminal", "json"]), default="terminal")
@click.option("--output", "-o", type=click.Path(), default=None, help="Save model as JSON file")
@click.pass_context
def scan(ctx, workspace: str, dataset: str, connection_string: str | None,
         tenant_id: str, client_id: str, client_secret: str, fmt: str, output: str | None):
    """Scan a live Power BI dataset via XMLA endpoint.

    Connects to Power BI service, pulls model metadata (tables, columns,
    measures, relationships), and converts to the same internal model as
    the TMDL parser. Results can be scored, checked, and reported on.

    Requires pyadomd or sempy-fabric:
      pip install daxops[xmla]    # pyadomd + azure-identity
      pip install daxops[fabric]  # sempy-fabric
    """
    from daxops.xmla import XmlaConnection, scan_xmla

    conn = XmlaConnection(
        workspace=workspace,
        dataset=dataset,
        connection_string=connection_string or "",
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
    )

    show_progress = fmt == "terminal"
    with progress_status(console, "Connecting to XMLA endpoint...", enabled=show_progress):
        model = scan_xmla(conn)

    model_dict = model.model_dump()

    if output:
        Path(output).write_text(json.dumps(model_dict, indent=2), encoding="utf-8")
        if fmt != "json":
            console.print(f"[green]Model saved to {output}")

    if fmt == "json":
        click.echo(json.dumps(model_dict, indent=2))
    else:
        table_ct = len(model.tables)
        col_ct = sum(len(t.columns) for t in model.tables)
        meas_ct = sum(len(t.measures) for t in model.tables)
        rel_ct = len(model.relationships)

        console.print(f"\n[bold]Scanned: {model.name}")
        console.print(f"  Tables:        {table_ct}")
        console.print(f"  Columns:       {col_ct}")
        console.print(f"  Measures:      {meas_ct}")
        console.print(f"  Relationships: {rel_ct}")

        if not output:
            console.print("\n[dim]Tip: use --output model.json to save, then score/check the JSON.[/dim]")


@cli.command()
@click.argument("before_path", type=click.Path(exists=True))
@click.argument("after_path", type=click.Path(exists=True))
@click.option("--format", "fmt", type=click.Choice(["terminal", "json"]), default="terminal")
def compare(before_path: str, after_path: str, fmt: str):
    """Compare two model versions — show improvement over time."""
    from daxops.parser.tmdl import parse_model
    from daxops.compare import compare_models, comparison_to_dict

    before = parse_model(before_path)
    after = parse_model(after_path)
    result = compare_models(before, after)

    if fmt == "json":
        click.echo(json.dumps(comparison_to_dict(result), indent=2))
    else:
        def _arrow(delta: int) -> str:
            if delta > 0:
                return f"[green]+{delta}[/green]"
            elif delta < 0:
                return f"[red]{delta}[/red]"
            return "[dim]0[/dim]"

        console.print("[bold]Model Comparison\n")
        console.print(f"  {'':20s} {'Before':>8s}  {'After':>8s}  {'Delta':>8s}")
        console.print(f"  {'Bronze Score':20s} {result.before.bronze:>8d}  {result.after.bronze:>8d}  {_arrow(result.bronze_delta)}")
        console.print(f"  {'Silver Score':20s} {result.before.silver:>8d}  {result.after.silver:>8d}  {_arrow(result.silver_delta)}")
        console.print(f"  {'Gold Score':20s} {result.before.gold:>8d}  {result.after.gold:>8d}  {_arrow(result.gold_delta)}")
        console.print(f"  {'Findings':20s} {result.before.findings_total:>8d}  {result.after.findings_total:>8d}  {_arrow(-result.findings_delta)}")

        if result.resolved_findings:
            console.print(f"\n  [green]Resolved ({len(result.resolved_findings)}):")
            for f in result.resolved_findings[:10]:
                console.print(f"    [green]- {f}")

        if result.new_findings:
            console.print(f"\n  [red]New ({len(result.new_findings)}):")
            for f in result.new_findings[:10]:
                console.print(f"    [red]+ {f}")

        console.print()
        if result.improved:
            console.print("[bold green]Model improved!")
        elif result.findings_delta == 0 and result.bronze_delta == 0:
            console.print("[dim]No change.")
        else:
            console.print("[bold red]Model regressed.")
