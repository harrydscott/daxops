# DaxOps

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![CI](https://img.shields.io/badge/CI-ready-green.svg)](#cicd-integration)

**Semantic model lifecycle tool for Power BI / Microsoft Fabric.**

DaxOps scores your TMDL models for AI readiness, runs health checks for DAX anti-patterns and missing metadata, generates documentation with LLMs, diffs model versions semantically, imports BPA rules, and generates badges.

## Installation

```bash
pip install daxops

# With LLM support for auto-documentation
pip install daxops[llm]
```

### From source

```bash
git clone https://github.com/your-org/daxops.git
cd daxops
pip install -e ".[dev]"
```

## Quick Start

```bash
# Score a model's AI readiness (accepts raw TMDL folder or .pbip project)
daxops score ./my-model/
daxops score ./my-pbip-project/

# Run health checks (with summary dashboard + recommendations)
daxops check ./my-model/

# JSON output for CI/CD pipelines
daxops score ./my-model/ --format json
daxops check ./my-model/ --format json

# Generate a full HTML report
daxops report ./my-model/ --format html

# Diff two model versions
daxops diff ./model-v1/ ./model-v2/

# Compare two versions (before/after improvement report)
daxops compare ./model-v1/ ./model-v2/

# Auto-generate descriptions with LLM
daxops document ./my-model/ --provider openai --model gpt-4o

# Watch for changes and re-run score+check
daxops watch ./my-model/

# Auto-fix common issues (rename dim/fact prefixes, hide keys)
daxops fix ./my-model/ --dry-run   # preview changes
daxops fix ./my-model/              # apply changes

# Save current findings as baseline — future checks only show new issues
daxops baseline ./my-model/
daxops check ./my-model/            # only new findings shown

# Run measure tests
daxops test ./my-model/ tests.yaml
daxops test ./my-model/ tests.yaml --reference ref-data.json

# Import Tabular Editor BPA rules
daxops bpa ./my-model/ BPARules.json

# Generate SVG badge for README
daxops badge ./my-model/ -o badge.svg
daxops badge ./my-model/ --style score --format json

# Quick model diagnostics
daxops info ./my-model/
daxops info ./my-model/ --format json

# Scan a live Power BI dataset via XMLA endpoint
daxops scan "My Workspace" "My Dataset"
daxops scan "My Workspace" "My Dataset" --output model.json

# Launch the interactive web app
daxops app --model-path ./my-model/
daxops app                             # opens folder picker in browser

# Register as Power BI Desktop External Tool (Windows)
daxops register-tool

# Create a sample model to try it out
daxops init ./sample/
```

## Interactive Web App

Launch a browser-based dashboard to explore your model's health and scores:

```bash
# Open with a specific model
daxops app --model-path ./my-model/

# Launch without a model (select folder in browser)
daxops app

# Custom port
daxops app --port 9000 --model-path ./my-model/

# Don't auto-open browser
daxops app --no-browser --model-path ./my-model/
```

The web app provides:
- **Dashboard** — score tiles (Bronze/Silver/Gold), finding summary, model stats
- **Findings List** — filterable by severity, rule, table, and free-text search
- **Settings** — browse filesystem and select a TMDL folder or .pbip project
- **Re-scan** — refresh model data without restarting the server

No build step required. The frontend uses Alpine.js and is served directly by FastAPI.

## Power BI Desktop External Tool (Windows)

DaxOps can register as a Power BI Desktop External Tool, appearing in the External Tools ribbon. When launched from PBI Desktop, it connects to the live model via the local Analysis Services instance.

### Setup

```bash
# Register DaxOps as an External Tool
daxops register-tool

# Remove registration
daxops register-tool --uninstall

# Custom External Tools folder path
daxops register-tool --path "C:\Custom\Path"
```

After registering, restart Power BI Desktop. DaxOps will appear in the **External Tools** ribbon. Clicking it launches the web app connected to your currently-open model.

### Connection Modes

| Mode | Read Source | Write Target | How |
|------|-----------|-------------|-----|
| **TMDL** | Files on disk | Files on disk | `daxops app --model-path ./my-model/` |
| **SSAS** | PBI Desktop (live) | Read-only | `daxops app --ssas-server localhost:12345 --database MyModel` |
| **Hybrid** | PBI Desktop (live) | Files on disk | Both `--ssas-server` and `--model-path` provided |

**Hybrid mode** is recommended when using the External Tool: the live model is read from SSAS (always up-to-date), while fixes are written to TMDL files on disk (safe, versioned, undo-able). PBI Desktop detects file changes and prompts you to reload.

DaxOps automatically detects the TMDL project folder from the SSAS workspace when possible. If auto-detection fails, set the model path in Settings or pass `--model-path`.

### Requirements

- **Windows only** — Power BI Desktop and SSAS are Windows-only
- **pyadomd** — `pip install daxops[xmla]` for SSAS connectivity
- TMDL folder mode works on any OS without pyadomd

## PBIP Project Support

DaxOps auto-detects whether you point it at a raw TMDL folder or a full `.pbip` project and handles both transparently. Supported input paths:

| Path Type | Example |
|-----------|---------|
| Raw TMDL folder | `./my-model/` (contains `model.tmdl`, `tables/`) |
| `.pbip` project root | `./MyProject/` (contains `*.pbip`, `*.SemanticModel/`) |
| `.SemanticModel` folder | `./MyProject/Sales.SemanticModel/` |
| `definition/` subfolder | `./MyProject/Sales.SemanticModel/definition/` |

```bash
# All of these work:
daxops score ./my-tmdl-folder/
daxops score ./my-pbip-project/
daxops check ./MyProject/Sales.SemanticModel/
```

## Exit Codes

All commands use consistent exit codes for CI/CD:

| Code | Meaning |
|------|---------|
| `0` | Pass — no issues found / thresholds met |
| `1` | Findings — issues found or thresholds breached |
| `2` | Runtime error — invalid path, parse error, etc. |

## Configuration

Create a `.daxops.yml` file in your project root to configure thresholds and rules:

```yaml
# .daxops.yml
score:
  bronze_min: 10    # minimum score to pass Bronze tier (default: 10)
  silver_min: 10    # minimum score to pass Silver tier (default: 10)
  gold_min: 8       # minimum score to pass Gold tier (default: 8)

check:
  max_errors: 0     # max errors before exit 1 (default: 0)
  max_warnings: ~   # max warnings before exit 1 (default: unlimited)

exclude_rules:      # rules to skip
  - UNUSED_COLUMNS
  - MISSING_FORMAT

exclude_tables:     # tables to skip in health checks
  - _Measures

severity: WARNING   # default minimum severity filter
```

DaxOps automatically discovers `.daxops.yml` by walking up from the model directory. You can also specify it explicitly:

```bash
daxops --config path/to/.daxops.yml score ./my-model/
```

## Scoring Framework

DaxOps evaluates your semantic model across three tiers:

| Tier | Criteria | Pass Threshold | Focus |
|------|----------|---------------|-------|
| Bronze | 7 criteria | >=10/14 | Naming, types, format strings, descriptions |
| Silver | 7 criteria | >=10/14 + Bronze | Table/column descriptions, display folders, synonyms |
| Gold | 6 criteria | >=8/12 + Silver | AI instructions, verified answers, cross-references |

## Health Checks

Each finding includes a specific fix recommendation.

| Rule | Severity | What it checks |
|------|----------|---------------|
| `NAMING_CONVENTION` | WARNING | dim/fact/stg prefixes, underscores |
| `MISSING_DESCRIPTION` | WARNING | Measures without `///` descriptions |
| `HIDDEN_KEYS` | WARNING | Key columns that aren't hidden |
| `MISSING_FORMAT` | INFO | Numeric columns without format strings |
| `UNUSED_COLUMNS` | INFO | Columns not referenced in measures |
| `DAX_COMPLEXITY` | WARNING | Nested CALCULATE/FILTER patterns |
| `MISSING_DATE_TABLE` | WARNING | No dedicated date table |
| `BIDIRECTIONAL_RELATIONSHIP` | WARNING | Bidirectional cross-filtering |
| `MISSING_DISPLAY_FOLDER` | INFO | Measures without display folders |
| `COLUMN_COUNT` | WARNING | Tables with >30 visible columns |

## Measure Testing

Define expected outputs for your DAX measures and validate them:

```yaml
# tests.yaml
tests:
  - measure: "Total Revenue"
    expected: 125000.50
    description: "Total revenue across all sales"
    tolerance: 0.01
  - measure: "Avg Order Value"
    expected: 250.00
    filter_context:
      Product.Category: "Electronics"
    tolerance: 1.0
```

```bash
# Static validation (measure exists, expression valid, filter columns exist)
daxops test ./my-model/ tests.yaml

# Compare against reference data
daxops test ./my-model/ tests.yaml --reference reference-data.json

# JSON output
daxops test ./my-model/ tests.yaml --format json
```

## BPA Rules Import

Import [Tabular Editor Best Practice Analyzer](https://github.com/TabularEditor/BestPracticeRules) rules and run them as health checks:

```bash
# Download official BPA rules
curl -O https://raw.githubusercontent.com/TabularEditor/BestPracticeRules/master/BPARules-PowerBI.json

# Run BPA rules against your model
daxops bpa ./my-model/ BPARules-PowerBI.json
daxops bpa ./my-model/ BPARules-PowerBI.json --format json
```

Currently mapped BPA rules: `META_AVOID_FLOAT`, `APPLY_FORMAT_STRING_MEASURES`, `APPLY_FORMAT_STRING_COLUMNS`, `META_SUMMARIZE_NONE`, `LAYOUT_COLUMNS_HIERARCHIES_DF`, `DAX_TODO`, `DAX_DIVISION_COLUMNS`. Unmapped rules (requiring Dynamic LINQ) are reported transparently.

## Badge Generation

Generate SVG badges for your README showing model tier status:

```bash
# Simple tier badge (Bronze/Silver/Gold)
daxops badge ./my-model/ -o badge.svg

# Detailed score badge
daxops badge ./my-model/ --style score -o badge.svg

# JSON tier info
daxops badge ./my-model/ --format json
```

## Comparison Report

Compare two model versions to track improvement over time:

```bash
daxops compare ./model-v1/ ./model-v2/
daxops compare ./model-v1/ ./model-v2/ --format json
```

Shows score deltas, new/resolved findings, and whether the model improved or regressed.

## Watch Mode

Re-runs score and health checks whenever TMDL files change:

```bash
daxops watch ./my-model/
daxops watch ./my-model/ --interval 2.0   # custom polling interval
```

Uses polling (no extra dependencies). Press Ctrl+C to stop.

## Auto-Fix

Automatically applies safe fixes to your model:

```bash
daxops fix ./my-model/ --dry-run   # preview what would change
daxops fix ./my-model/              # apply fixes
daxops fix ./my-model/ --format json
```

Current auto-fixes:
- **NAMING_CONVENTION** — removes dim/fact/stg/vw/tbl/dbo prefixes from table names
- **HIDDEN_KEYS** — adds `isHidden` to columns ending in ID, Key, or SK

## Baseline/Suppress

Save current findings as a baseline so future runs only show new issues:

```bash
# Save current state
daxops baseline ./my-model/

# Future checks only show NEW findings
daxops check ./my-model/

# Skip baseline filtering
daxops check ./my-model/ --no-baseline
```

The baseline is stored in `.daxops-baseline.json` inside the model directory.

## CI/CD Integration

### GitHub Actions

DaxOps ships with a ready-to-use workflow. Copy `.github/workflows/daxops-ci.yml` to your repo, or add these steps to your existing workflow:

```yaml
- name: Install DaxOps
  run: pip install daxops

- name: Score model
  run: daxops score ./model/ --format json

- name: Check model
  run: daxops check ./model/ --format json
```

The workflow automatically:
- Detects your TMDL model directory
- Runs score and check with JSON output
- Posts results to the GitHub Actions step summary
- Uploads JSON artifacts for downstream use
- Fails the build if thresholds are breached

### Azure DevOps Pipelines

Copy `azure-pipelines-daxops.yml` to your repo. It auto-detects your model path, runs score + check, and publishes JSON artifacts:

```yaml
# azure-pipelines-daxops.yml (included in this repo)
# Triggers on changes to *.tmdl or .daxops.yml files
# Configurable via the modelPath parameter
```

### Pre-commit Hook

Add DaxOps to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/your-org/daxops
    rev: v0.2.0
    hooks:
      - id: daxops-check
        args: ['./path/to/model/']
      - id: daxops-score
        args: ['./path/to/model/']
```

Available hooks:
- `daxops-check` — runs health checks, fails on findings
- `daxops-score` — scores AI readiness, fails if below Bronze

## Auto-Documentation

Generate descriptions for undocumented objects using an LLM:

```bash
# Dry run — see what would be documented
daxops document ./my-model/ --dry-run

# Generate with OpenAI
export OPENAI_API_KEY=sk-...
daxops document ./my-model/ --provider openai --model gpt-4o
```

## Sample Model

DaxOps ships with a Contoso Sales sample model containing intentional issues:

```bash
daxops score samples/contoso-sales/
daxops check samples/contoso-sales/
```

## XMLA Endpoint Scanner

Scan live Power BI datasets directly from the service via XMLA endpoint:

```bash
# Install XMLA dependencies
pip install daxops[xmla]    # pyadomd + azure-identity
# OR
pip install daxops[fabric]  # sempy-fabric

# Scan a dataset
daxops scan "My Workspace" "Sales Dataset"
daxops scan "My Workspace" "Sales Dataset" --format json
daxops scan "My Workspace" "Sales Dataset" --output model.json

# Use environment variables for authentication
export AZURE_TENANT_ID=...
export AZURE_CLIENT_ID=...
export AZURE_CLIENT_SECRET=...
daxops scan "My Workspace" "Sales Dataset"
```

The scanned model is converted to the same internal format as the TMDL parser, so all scoring, health checks, and reporting work identically on live models.

## VS Code Extension

A VS Code extension stub is included in `vscode-daxops/`. It provides:

- 8 commands accessible via Command Palette (Score, Check, Fix, Report, Watch, Badge, Baseline)
- TMDL language registration (`.tmdl` file type)
- Run-on-save option for automatic health checks
- Auto-detection of TMDL models in workspace

See [`vscode-daxops/README.md`](vscode-daxops/README.md) for setup instructions.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT — see [LICENSE](LICENSE).
