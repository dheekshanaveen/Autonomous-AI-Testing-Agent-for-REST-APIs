"""Tests for verifier module."""

from pathlib import Path
from local_agent.analyzer import TestCandidateAnalyzer
from local_agent.generator import TestGenerator
from local_agent.intake import validate_repository_folder
from local_agent.inventory import build_project_inventory
from local_agent.models import FindingStatus
from local_agent.runner import IsolatedRunner
from local_agent.verifier import FindingVerifier


def test_verifier_confirms_reproducible_failure(sample_python_repo_path, temp_dir):
    source = validate_repository_folder(str(sample_python_repo_path))
    inv = build_project_inventory(source)
    candidates = TestCandidateAnalyzer.analyze(inv)

    runner = IsolatedRunner(timeout_seconds=5.0)
    verifier = FindingVerifier(runner)

    # Find the zero division candidate for compute_moving_average
    zero_cand = [
        c for c in candidates
        if c.symbol_name == "compute_moving_average" and c.category == "ast_heuristic"
    ][0]

    test_file = TestGenerator.generate_test(zero_cand, temp_dir, sample_python_repo_path)
    finding = verifier.verify_candidate(zero_cand, test_file, sample_python_repo_path)

    # Acceptance criteria: Must be VERIFIED_FAILURE because it fails run 1 and reproduces on replay run 2
    assert finding.status == FindingStatus.VERIFIED_FAILURE
    assert "ZeroDivisionError" in finding.observed_behavior
    assert finding.run1_result is not None
    assert finding.run2_replay_result is not None
    assert finding.run1_result.passed is False
    assert finding.run2_replay_result.passed is False


def test_verifier_classifies_setup_gap(sample_unsupported_repo_path, temp_dir):
    source = validate_repository_folder(str(sample_unsupported_repo_path))
    inv = build_project_inventory(source)
    candidates = TestCandidateAnalyzer.analyze(inv)

    runner = IsolatedRunner(timeout_seconds=5.0)
    verifier = FindingVerifier(runner)

    cand = candidates[0]
    test_file = TestGenerator.generate_test(cand, temp_dir, sample_unsupported_repo_path)
    finding = verifier.verify_candidate(cand, test_file, sample_unsupported_repo_path)

    # Acceptance criteria: report does not mark as verified when setup fails
    assert finding.status == FindingStatus.SETUP_GAP
    assert "Environment setup incomplete" in finding.reason_unconfirmed


def test_verifier_fix_verification(sample_python_repo_path, sample_python_fixed_path, temp_dir):
    source = validate_repository_folder(str(sample_python_repo_path))
    inv = build_project_inventory(source)
    candidates = TestCandidateAnalyzer.analyze(inv)

    runner = IsolatedRunner(timeout_seconds=5.0)
    verifier = FindingVerifier(runner)

    zero_cand = [
        c for c in candidates
        if c.symbol_name == "compute_moving_average" and c.category == "ast_heuristic"
    ][0]

    test_file = TestGenerator.generate_test(zero_cand, temp_dir, sample_python_repo_path)

    is_verified_fix, details = verifier.verify_fix(
        test_file=test_file,
        language="python",
        faulty_repo=sample_python_repo_path,
        fixed_repo=sample_python_fixed_path,
    )

    # Acceptance criteria: test fails on faulty and passes on fixed
    assert is_verified_fix is True
    assert details["faulty_passed"] is False
    assert details["fixed_passed"] is True

