# DaxOps

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![CI](https://img.shields.io/badge/CI-ready-green.svg)](#cicd-integration)

**Semantic model lifecycle tool for Power BI / Microsoft Fabric.**

DaxOps scores your TMDL models for AI readiness, runs health checks for DAX anti-patterns and missing metadata, generates documentation with LLMs, and diffs model versions semantically.

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

# Run health checks
daxops check ./my-model/

# JSON output for CI/CD pipelines
daxops score ./my-model/ --format json
daxops check ./my-model/ --format json

# Generate a full HTML report
daxops report ./my-model/ --format html

# Diff two model versions
daxops diff ./model-v1/ ./model-v2/

# Auto-generate descriptions with LLM
daxops document ./my-model/ --provider openai --model gpt-4o

# Create a sample model to try it out
daxops init ./sample/
```

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
| 🥉 Bronze | 7 criteria | ≥10/14 | Naming, types, format strings, descriptions |
| 🥈 Silver | 7 criteria | ≥10/14 + Bronze | Table/column descriptions, display folders, synonyms |
| 🥇 Gold | 6 criteria | ≥8/12 + Silver | AI instructions, verified answers, cross-references |

## Health Checks

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

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT — see [LICENSE](LICENSE).
