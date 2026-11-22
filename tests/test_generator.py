"""Tests for test generator module."""

import ast
from pathlib import Path
from local_agent.analyzer import TestCandidateAnalyzer
from local_agent.generator import TestGenerator
from local_agent.intake import validate_repository_folder
from local_agent.inventory import build_project_inventory


def test_generator_python_syntax_validity(sample_python_repo_path, temp_dir):
    source = validate_repository_folder(str(sample_python_repo_path))
    inv = build_project_inventory(source)
    candidates = TestCandidateAnalyzer.analyze(inv)

    for cand in candidates[:5]:
        test_file = TestGenerator.generate_test(cand, temp_dir, sample_python_repo_path)
        assert test_file.exists()
        assert test_file.parent.resolve() == (temp_dir / "generated_tests").resolve()

        # Verify generated Python test is syntactically valid
        content = test_file.read_text(encoding="utf-8")
        parsed = ast.parse(content)
        assert parsed is not None
        assert "pytest" in content


def test_generator_js_syntax(sample_js_repo_path, temp_dir):
    source = validate_repository_folder(str(sample_js_repo_path))
    inv = build_project_inventory(source)
    candidates = TestCandidateAnalyzer.analyze(inv)

    js_cands = [c for c in candidates if c.language == "javascript"]
    assert len(js_cands) > 0

    test_file = TestGenerator.generate_test(js_cands[0], temp_dir, sample_js_repo_path)
    assert test_file.exists()
    content = test_file.read_text(encoding="utf-8")
    assert "node:test" in content
    assert "node:assert/strict" in content

