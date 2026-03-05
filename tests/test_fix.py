"""Tests for auto-fix mode."""
import shutil
from pathlib import Path

from daxops.fix import run_fixes, _fix_table_prefix, _fix_hidden_keys

FIXTURES = Path(__file__).parent / "fixtures" / "sample-model"


def test_fix_dry_run_no_changes():
    results = run_fixes(FIXTURES, dry_run=True)
    # Should find things to fix (dim/fact prefixes and unhidden keys)
    assert len(results) > 0


def test_fix_dry_run_does_not_modify_files():
    # Read original content
    tables_dir = FIXTURES / "tables"
    originals = {}
    for f in tables_dir.glob("*.tmdl"):
        originals[f.name] = f.read_text(encoding="utf-8")

    run_fixes(FIXTURES, dry_run=True)

    # Verify nothing changed
    for f in tables_dir.glob("*.tmdl"):
        assert f.read_text(encoding="utf-8") == originals[f.name]


def test_fix_table_prefix_removes_dim():
    content = "table dimCustomer\n\tlineageTag: abc\n"
    new_content, results = _fix_table_prefix(content, Path("dimCustomer.tmdl"))
    assert "dimCustomer" not in new_content.split("\n")[0]
    assert "'Customer'" in new_content.split("\n")[0]
    assert len(results) >= 1
    assert results[0].rule == "NAMING_CONVENTION"


def test_fix_table_prefix_removes_fact():
    content = "table factOrders\n\tlineageTag: abc\n"
    new_content, results = _fix_table_prefix(content, Path("factOrders.tmdl"))
    assert "factOrders" not in new_content.split("\n")[0]
    assert "'Orders'" in new_content.split("\n")[0]


def test_fix_table_prefix_no_prefix():
    content = "table Sales\n\tlineageTag: abc\n"
    new_content, results = _fix_table_prefix(content, Path("Sales.tmdl"))
    assert new_content == content
    assert len(results) == 0


def test_fix_hidden_keys_adds_ishidden():
    content = "table Sales\n\tcolumn 'SalesKey'\n\t\tdataType: int64\n\tcolumn 'Amount'\n\t\tdataType: decimal\n"
    new_content, results = _fix_hidden_keys(content, Path("Sales.tmdl"))
    assert "isHidden" in new_content
    key_fixes = [r for r in results if r.rule == "HIDDEN_KEYS"]
    assert len(key_fixes) == 1
    assert "SalesKey" in key_fixes[0].description


def test_fix_hidden_keys_skips_already_hidden():
    content = "table Sales\n\tcolumn 'SalesKey'\n\t\tdataType: int64\n\t\tisHidden\n\tcolumn 'Amount'\n\t\tdataType: decimal\n"
    new_content, results = _fix_hidden_keys(content, Path("Sales.tmdl"))
    key_fixes = [r for r in results if r.rule == "HIDDEN_KEYS"]
    assert len(key_fixes) == 0


def test_fix_hidden_keys_does_not_hide_non_key():
    content = "table Sales\n\tcolumn 'Amount'\n\t\tdataType: decimal\n"
    new_content, results = _fix_hidden_keys(content, Path("Sales.tmdl"))
    assert "isHidden" not in new_content
    assert len(results) == 0


def test_fix_applies_changes_to_copy(tmp_path):
    """Test that fix actually writes changes when not dry-run."""
    # Copy fixture to temp
    model_dir = tmp_path / "model"
    shutil.copytree(FIXTURES, model_dir)

    results = run_fixes(model_dir, dry_run=False)
    applied = [r for r in results if r.applied]
    assert len(applied) > 0

    # Verify files were actually modified
    tables_dir = model_dir / "tables"
    all_content = ""
    for f in tables_dir.glob("*.tmdl"):
        all_content += f.read_text(encoding="utf-8")

    # At least some key columns should now be hidden
    assert "isHidden" in all_content


def test_fix_table_prefix_with_underscore():
    content = "table dim_Customer\n\tlineageTag: abc\n"
    new_content, results = _fix_table_prefix(content, Path("dim_Customer.tmdl"))
    assert "'Customer'" in new_content.split("\n")[0]


def test_fix_table_prefix_with_quotes():
    content = "table 'dimCustomer'\n\tlineageTag: abc\n"
    new_content, results = _fix_table_prefix(content, Path("dimCustomer.tmdl"))
    assert "'Customer'" in new_content.split("\n")[0]
