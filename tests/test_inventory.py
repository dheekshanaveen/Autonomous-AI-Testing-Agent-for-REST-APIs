"""Tests for inventory module."""

from pathlib import Path
from local_agent.intake import validate_repository_folder
from local_agent.inventory import build_project_inventory, PythonInspector, JavaScriptInspector


def test_inventory_python_repo(sample_python_repo_path):
    source = validate_repository_folder(str(sample_python_repo_path))
    inv = build_project_inventory(source)

    assert "python" in inv.languages
    assert any("pyproject.toml" in m for m in inv.manifests)
    assert len(inv.source_files) >= 3

    symbols_by_name = {s.name: s for s in inv.symbols}
    assert "compute_moving_average" in symbols_by_name
    assert "calculate_ratio" in symbols_by_name
    assert "transform_records" in symbols_by_name
    assert "StreamSession" in symbols_by_name

    # Check contracts
    ratio_sym = symbols_by_name["calculate_ratio"]
    assert len(ratio_sym.contracts) > 0
    assert any(c.kind == "raises" and c.target == "ValueError" for c in ratio_sym.contracts)

    # Check AST risks
    avg_sym = symbols_by_name["compute_moving_average"]
    assert "zero_division" in avg_sym.risk_flags


def test_inventory_javascript_repo(sample_js_repo_path):
    source = validate_repository_folder(str(sample_js_repo_path))
    inv = build_project_inventory(source)

    assert "javascript" in inv.languages
    assert any("package.json" in m for m in inv.manifests)

    symbols_by_name = {s.name: s for s in inv.symbols}
    assert "extractTokens" in symbols_by_name
    assert "TokenBuffer" in symbols_by_name

    extract_sym = symbols_by_name["extractTokens"]
    assert len(extract_sym.parameters) == 2
    assert extract_sym.parameters[0].name == "text"


def test_python_inspector_ast_risks(temp_dir):
    code = """
def divide_items(items, denom):
    return items[0] / denom
"""
    f = temp_dir / "risky.py"
    f.write_text(code, encoding="utf-8")

    symbols = PythonInspector.inspect_file(f, "risky.py")
    assert len(symbols) == 1
    sym = symbols[0]
    assert "zero_division" in sym.risk_flags
    assert "empty_sequence" in sym.risk_flags

