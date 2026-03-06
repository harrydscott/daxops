# DaxOps VS Code Extension

Semantic model lifecycle tool for Power BI / Microsoft Fabric — run DaxOps commands directly from VS Code.

## Prerequisites

Install the DaxOps CLI:

```bash
pip install daxops
```

## Features

- **Score Model** — evaluate AI readiness (Bronze/Silver/Gold)
- **Check Model** — run health checks for DAX anti-patterns
- **Fix Model** — auto-fix common issues (naming, hidden keys)
- **Generate Report** — full HTML report
- **Watch Mode** — re-run checks on file save
- **Badge Generation** — SVG badges for README
- **Baseline** — save current findings, only show new issues

## Commands

Open the Command Palette (`Cmd+Shift+P` / `Ctrl+Shift+P`) and type "DaxOps":

| Command | Description |
|---------|-------------|
| `DaxOps: Score Model` | Score model AI readiness |
| `DaxOps: Check Model` | Run health checks |
| `DaxOps: Fix Model` | Apply auto-fixes |
| `DaxOps: Fix Model (Dry Run)` | Preview auto-fixes |
| `DaxOps: Generate Report` | Generate HTML report |
| `DaxOps: Watch Mode` | Re-run on file changes |
| `DaxOps: Generate Badge` | Create SVG badge |
| `DaxOps: Save Baseline` | Save current findings |

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `daxops.pythonPath` | `python` | Path to Python with daxops installed |
| `daxops.modelPath` | (auto-detect) | Path to TMDL model directory |
| `daxops.runOnSave` | `false` | Auto-run checks on `.tmdl` file save |

## TMDL Language Support

The extension registers `.tmdl` as a recognized file type in VS Code.

## Development

```bash
cd vscode-daxops
npm install
npm run compile
# Press F5 in VS Code to launch extension dev host
```

## Building

```bash
npm run package  # creates .vsix file
```
