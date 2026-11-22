"""Tests for analyzer module."""

from local_agent.analyzer import TestCandidateAnalyzer
from local_agent.intake import validate_repository_folder
from local_agent.inventory import build_project_inventory


def test_analyzer_generates_candidates_for_python(sample_python_repo_path):
    source = validate_repository_folder(str(sample_python_repo_path))
    inv = build_project_inventory(source)
    candidates = TestCandidateAnalyzer.analyze(inv)

    assert len(candidates) > 0
    categories = {c.category for c in candidates}
    assert "boundary_value" in categories
    assert "malformed_input" in categories

    # Verify zero-division heuristic candidate exists
    zero_cands = [c for c in candidates if c.category == "ast_heuristic"]
    assert len(zero_cands) > 0
    assert any(c.symbol_name in {"compute_moving_average", "calculate_ratio"} for c in zero_cands)

    # Verify stateful candidates exist
    stateful_cands = [c for c in candidates if c.is_stateful]
    assert len(stateful_cands) > 0
    assert any(c.symbol_name == "StreamSession" for c in stateful_cands)

    # Verify contract violation candidates exist
    contract_cands = [c for c in candidates if c.category == "contract_violation"]
    assert len(contract_cands) > 0


def test_analyzer_generates_candidates_for_js(sample_js_repo_path):
    source = validate_repository_folder(str(sample_js_repo_path))
    inv = build_project_inventory(source)
    candidates = TestCandidateAnalyzer.analyze(inv)

    assert len(candidates) > 0
    token_cands = [c for c in candidates if c.symbol_name == "extractTokens"]
    assert len(token_cands) > 0
    # Check for null payload candidate
    assert any(c.inputs.get("text") is None for c in token_cands)

