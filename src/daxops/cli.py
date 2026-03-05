"""Click-based CLI for DaxOps."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table as RichTable

from daxops import __version__

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
def cli():
    """DaxOps — Semantic Model Lifecycle Tool for Power BI / Microsoft Fabric."""


@cli.command()
@click.argument("model_path", type=click.Path(exists=True))
@click.option("--format", "fmt", type=click.Choice(["terminal", "json", "markdown"]), default="terminal")
def score(model_path: str, fmt: str):
    """Score a model's AI readiness (Bronze/Silver/Gold)."""
    from daxops.parser.tmdl import parse_model
    from daxops.scoring import score_bronze, score_silver, score_gold
    from daxops.report.markdown import generate_score_report

    model = parse_model(model_path)
    bronze = score_bronze(model)
    silver = score_silver(model)
    gold = score_gold(model)

    b = sum(c.score for c in bronze)
    s = sum(c.score for c in silver)
    g = sum(c.score for c in gold)
    summary = {
        "bronze_score": b, "silver_score": s, "gold_score": g,
        "bronze_pass": b >= 10, "silver_pass": b >= 10 and s >= 10,
        "gold_pass": b >= 10 and s >= 10 and g >= 8,
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
        _render_score_terminal(bronze, silver, gold)

    if not summary["bronze_pass"]:
        sys.exit(1)


def _render_score_terminal(bronze, silver, gold):
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
    console.print()
    if b >= 10 and s >= 10 and g >= 8:
        console.print("[bold bright_yellow]🥇 Gold tier achieved!")
    elif b >= 10 and s >= 10:
        console.print("[bold white]🥈 Silver tier achieved!")
    elif b >= 10:
        console.print("[bold yellow]🥉 Bronze tier achieved!")
    else:
        console.print(f"[dim]⬜ No tier achieved (Bronze needs {10 - b} more points)[/dim]")


@cli.command()
@click.argument("model_path", type=click.Path(exists=True))
@click.option("--format", "fmt", type=click.Choice(["terminal", "json", "markdown"]), default="terminal")
@click.option("--severity", type=click.Choice(["ERROR", "WARNING", "INFO"]), default=None, help="Minimum severity to show")
def check(model_path: str, fmt: str, severity: str | None):
    """Run health checks on a TMDL model."""
    from daxops.parser.tmdl import parse_model
    from daxops.health.rules import run_health_checks, Severity
    from daxops.report.markdown import generate_health_report

    model = parse_model(model_path)
    findings = run_health_checks(model)

    if severity:
        sev_order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
        threshold = sev_order[severity]
        findings = [f for f in findings if sev_order[f.severity.value] <= threshold]

    if fmt == "json":
        data = [{"rule": f.rule, "severity": f.severity.value, "message": f.message, "object": f.object_path} for f in findings]
        click.echo(json.dumps(data, indent=2))
    elif fmt == "markdown":
        click.echo(generate_health_report(findings))
    else:
        if not findings:
            console.print("[green]✅ No issues found!")
        else:
            sev_colors = {"ERROR": "red", "WARNING": "yellow", "INFO": "blue"}
            table = RichTable(title=f"Health Check — {len(findings)} findings")
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

    # Exit code: 1 if any findings (warnings or errors)
    if findings:
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

    if not result.has_changes:
        console.print("[green]No changes detected.")
        return

    if fmt == "json":
        data = [{"category": c.category, "type": c.change_type, "path": c.path, "details": c.details} for c in result.changes]
        click.echo(json.dumps(data, indent=2))
    else:
        type_colors = {"added": "green", "removed": "red", "modified": "yellow"}
        type_icons = {"added": "+", "removed": "-", "modified": "~"}
        for c in result.changes:
            color = type_colors.get(c.change_type, "white")
            icon = type_icons.get(c.change_type, " ")
            detail = f" ({c.details})" if c.details else ""
            console.print(f"  [{color}]{icon} [{c.category}] {c.path}{detail}")


@cli.command()
@click.argument("model_path", type=click.Path(exists=True))
@click.option("--format", "fmt", type=click.Choice(["html", "markdown"]), default="html")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output file path")
def report(model_path: str, fmt: str, output: str | None):
    """Generate a full report (score + health checks)."""
    from daxops.parser.tmdl import parse_model
    from daxops.scoring import score_bronze, score_silver, score_gold
    from daxops.health.rules import run_health_checks
    from daxops.report.markdown import generate_score_report, generate_health_report
    from daxops.report.html import generate_html_report

    model = parse_model(model_path)
    bronze = score_bronze(model)
    silver = score_silver(model)
    gold = score_gold(model)
    findings = run_health_checks(model)

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
@click.option("--provider", type=click.Choice(["openai"]), default="openai")
@click.option("--model", "llm_model", default="gpt-4o")
@click.option("--api-key", envvar="OPENAI_API_KEY", default=None)
@click.option("--dry-run", is_flag=True, help="Show what would be documented without calling LLM")
def document(model_path: str, provider: str, llm_model: str, api_key: str | None, dry_run: bool):
    """Auto-generate descriptions for undocumented objects using LLM."""
    from daxops.parser.tmdl import parse_model

    model = parse_model(model_path)

    # Find undocumented objects
    undoc = []
    for t in model.tables:
        if not t.description:
            undoc.append(f"[table] {t.name}")
        for m in t.measures:
            if not m.description:
                undoc.append(f"[measure] {t.name}.[{m.name}]")
        for c in t.columns:
            if not c.description and not c.is_hidden:
                undoc.append(f"[column] {t.name}.{c.name}")

    if not undoc:
        console.print("[green]All objects are documented! Nothing to do.")
        return

    console.print(f"Found {len(undoc)} undocumented objects:")
    for u in undoc:
        console.print(f"  [dim]{u}[/dim]")

    if dry_run:
        console.print("\n[yellow]Dry run — no LLM calls made.")
        return

    from daxops.document.generator import generate_descriptions
    results = generate_descriptions(model, provider, llm_model, api_key)

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
