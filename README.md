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
# Score a model's AI readiness
daxops score ./my-model/

# Run health checks
daxops check ./my-model/

# Generate a full HTML report
daxops report ./my-model/ --format html

# Diff two model versions
daxops diff ./model-v1/ ./model-v2/

# Auto-generate descriptions with LLM
daxops document ./my-model/ --provider openai --model gpt-4o

# Create a sample model to try it out
daxops init ./sample/
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

```bash
# Exit code 0 = pass, 1 = errors found
daxops check ./my-model/ --format json --severity ERROR

# JSON output for automation
daxops score ./my-model/ --format json
```

### GitHub Actions Example

```yaml
- name: Check semantic model
  run: |
    pip install daxops
    daxops check ./model/ --severity ERROR
    daxops score ./model/ --format json > score.json
```

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
