"""Automated Tests for Bug Verifier and Test Minimizer (Step 6).

Verifies:
1. BugVerifier confirms reproducible bugs after repeated clean runs.
2. BugVerifier flags inconsistent / flaky failures as inconclusive without false confirmations.
3. BugVerifier flags non-reproducible failures as not reproducible.
4. TestMinimizer removes unnecessary requests from a multi-step sequence.
5. TestMinimizer preserves the exact same BOLA vulnerability and user identities.
6. TestMinimizer preserves critical data dependencies (prerequisite logins and resource creation).
7. TestMinimizer removes unnecessary payload fields from request bodies.
8. TestMinimizer rejects reductions that lose the original bug.
9. Reduction ratio is calculated accurately: 1 - (minimized / original).
10. Execution failures, connection errors, and timeouts are handled gracefully without crashes.
11. Full end-to-end integration against the running local Sample Shopping API.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple
import pytest

from agent.executor import ExecutionResult, RequestTrace, ResponseTrace, RequestExecutor
from agent.oracles import BugFinding, BOLAOracle
from agent.verifier import BugVerifier, VerificationResult
from agent.minimizer import (
    TestSequence,
    TestSequenceStep,
    TestMinimizer,
    MinimizationResult,
)


# ------------------------------------------------------------------------------
# Test Fixtures & Helpers
# ------------------------------------------------------------------------------

def make_dummy_finding(bug_type: str = "BOLA_VIOLATION") -> BugFinding:
    return BugFinding(
        bug_type=bug_type,
        severity="CRITICAL",
        endpoint="/orders/{order_id}",
        method="GET",
        expected_behavior="Access denied",
        actual_response={"status_code": 200},
        explanation="Test finding",
        evidence={"resource_id": "ord-1"},
        is_confirmed=True,
    )


# ------------------------------------------------------------------------------
# 1. Bug Verifier Tests
# ------------------------------------------------------------------------------

def test_verifier_confirms_reproducible_bug():
    """Verify that a defect reproducing in 2/2 clean runs is marked CONFIRMED_REPRODUCIBLE."""
    verifier = BugVerifier()
    finding = make_dummy_finding()

    # Evaluator that always succeeds
    def always_reproduces():
        return True, finding

    result = verifier.verify_evaluator(
        evaluator_fn=always_reproduces,
        bug_type="BOLA_VIOLATION",
        repeat_count=2,
    )

    assert result.is_reproducible is True
    assert result.status == "CONFIRMED_REPRODUCIBLE"
    assert result.runs_evaluated == 2
    assert result.successful_runs == 2
    assert result.failed_runs == 0
    assert "reproduced consistently" in result.details


def test_verifier_flags_inconsistent_flaky_failure():
    """Verify that an inconsistent failure (reproduced 1/2 runs) is flagged as FLAKY."""
    verifier = BugVerifier()
    finding = make_dummy_finding()

    call_count = 0

    def flaky_evaluator():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return True, finding
        return False, None

    result = verifier.verify_evaluator(
        evaluator_fn=flaky_evaluator,
        bug_type="BOLA_VIOLATION",
        repeat_count=2,
    )

    assert result.is_reproducible is False
    assert result.status == "FLAKY"
    assert result.successful_runs == 1
    assert result.failed_runs == 1
    assert "flaky" in result.details.lower()


def test_verifier_flags_non_reproducible_failure():
    """Verify that a defect that fails to reproduce across all runs is NOT_REPRODUCIBLE."""
    verifier = BugVerifier()

    def never_reproduces():
        return False, None

    result = verifier.verify_evaluator(
        evaluator_fn=never_reproduces,
        bug_type="SERVER_ERROR_5XX",
        repeat_count=2,
    )

    assert result.is_reproducible is False
    assert result.status == "NOT_REPRODUCIBLE"
    assert result.successful_runs == 0
    assert result.failed_runs == 2


# ------------------------------------------------------------------------------
# 2. Test Minimizer Unit & Algorithmic Tests
# ------------------------------------------------------------------------------

def test_reduction_ratio_calculation():
    """Verify the reduction ratio formula: 1 - (minimized / original)."""
    orig_seq = TestSequence.from_bola_scenario(with_noise=True)
    assert orig_seq.request_count == 10

    min_seq = TestSequence.from_bola_scenario(with_noise=False)
    assert min_seq.request_count == 4

    # 10 to 4 = 60% reduction
    ratio = 1.0 - (4 / 10)
    assert abs(ratio - 0.6) < 1e-6

    res = MinimizationResult(
        target_bug_type="BOLA_VIOLATION",
        original_request_count=10,
        minimized_request_count=4,
        reduction_ratio=ratio,
        reduction_percentage=ratio * 100.0,
        is_reduced=True,
        original_sequence=orig_seq,
        minimized_sequence=min_seq,
    )
    assert res.reduction_percentage == 60.0
    assert "60.0%" in res.summary()


def test_minimizer_reports_already_minimal_test():
    """Verify that a test that cannot be reduced is honestly reported as unchanged."""
    seq = TestSequence.from_bola_scenario(with_noise=False)
    assert seq.request_count == 4

    minimizer = TestMinimizer()
    finding = make_dummy_finding()

    # Evaluator requires all 4 steps to reproduce
    def mock_evaluator(cand: TestSequence):
        if cand.request_count == 4:
            return True, finding
        return False, None

    result = minimizer.minimize_sequence(
        sequence=seq,
        evaluator_fn=mock_evaluator,
        target_bug_type="BOLA_VIOLATION",
    )

    assert result.is_reduced is False
    assert result.minimized_request_count == 4
    assert result.reduction_ratio == 0.0
    assert "ALREADY MINIMAL" in result.format_report()


def test_minimizer_removes_unnecessary_requests_mocked():
    """Verify that delta-debugging removes unneeded dummy requests."""
    steps = [
        TestSequenceStep(name="Noise 1", method="GET", path="/health"),
        TestSequenceStep(name="Essential A", method="POST", path="/auth/login"),
        TestSequenceStep(name="Noise 2", method="GET", path="/health"),
        TestSequenceStep(name="Essential B", method="POST", path="/orders"),
        TestSequenceStep(name="Noise 3", method="GET", path="/health"),
    ]
    seq = TestSequence(name="Mixed Sequence", steps=steps)
    minimizer = TestMinimizer()
    finding = make_dummy_finding()

    def mock_evaluator(cand: TestSequence):
        names = {s.name for s in cand.steps}
        # Only reproduces if Essential A and Essential B are present
        if "Essential A" in names and "Essential B" in names:
            return True, finding
        return False, None

    result = minimizer.minimize_sequence(
        sequence=seq,
        evaluator_fn=mock_evaluator,
        target_bug_type="BOLA_VIOLATION",
    )

    assert result.is_reduced is True
    assert result.original_request_count == 5
    assert result.minimized_request_count == 2
    assert result.reduction_ratio == 0.6  # 1 - (2/5) = 60%
    assert len(result.removed_step_names) == 3
    assert set(result.removed_step_names) == {"Noise 1", "Noise 2", "Noise 3"}


def test_minimizer_removes_unnecessary_payload_fields_mocked():
    """Verify that delta-debugging prunes non-essential fields from JSON payloads."""
    step = TestSequenceStep(
        name="Create Order",
        method="POST",
        path="/orders",
        json_body={
            "item_name": "Laptop",
            "quantity": 1,
            "total_price": 999.99,
            "redundant_note": "Handle with care",
            "gift_wrap": True,
        },
    )
    seq = TestSequence(name="Payload Sequence", steps=[step])
    minimizer = TestMinimizer()
    finding = make_dummy_finding()

    def mock_evaluator(cand: TestSequence):
        body = cand.steps[0].json_body
        # Requires item_name and total_price, but redundant_note and gift_wrap are optional
        if "item_name" in body and "total_price" in body:
            return True, finding
        return False, None

    result = minimizer.minimize_sequence(
        sequence=seq,
        evaluator_fn=mock_evaluator,
        target_bug_type="SCHEMA_MISMATCH",
    )

    assert result.is_reduced is True
    min_body = result.minimized_sequence.steps[0].json_body
    assert "item_name" in min_body
    assert "total_price" in min_body
    assert "redundant_note" not in min_body
    assert "gift_wrap" not in min_body
    assert len(result.removed_payload_fields) == 3  # quantity, redundant_note, gift_wrap


def test_minimizer_rejects_reduction_that_loses_bug():
    """Verify that a candidate reduction is rejected if the target bug does not occur."""
    steps = [
        TestSequenceStep(name="Req 1", method="POST", path="/step1"),
        TestSequenceStep(name="Req 2", method="POST", path="/step2"),
    ]
    seq = TestSequence(name="Two Step Seq", steps=steps)
    minimizer = TestMinimizer()
    finding = make_dummy_finding()

    def mock_evaluator(cand: TestSequence):
        # Only reproduces if BOTH steps are present
        if len(cand.steps) == 2:
            return True, finding
        return False, None

    result = minimizer.minimize_sequence(
        sequence=seq,
        evaluator_fn=mock_evaluator,
        target_bug_type="BOLA_VIOLATION",
    )

    assert result.is_reduced is False
    assert result.minimized_request_count == 2
    assert result.reduction_ratio == 0.0


def test_minimizer_handles_evaluator_exceptions_gracefully():
    """Verify that exceptions during candidate execution do not crash the minimizer."""
    steps = [
        TestSequenceStep(name="Noise", method="GET", path="/health"),
        TestSequenceStep(name="Essential", method="POST", path="/auth/login"),
    ]
    seq = TestSequence(name="Error Handling Seq", steps=steps)
    minimizer = TestMinimizer()
    finding = make_dummy_finding()

    call_count = 0

    def error_prone_evaluator(cand: TestSequence):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return True, finding  # Initial check succeeds
        if any(s.name == "Noise" for s in cand.steps):
            raise ConnectionError("Simulated network timeout during candidate evaluation")
        return True, finding

    result = minimizer.minimize_sequence(
        sequence=seq,
        evaluator_fn=error_prone_evaluator,
        target_bug_type="BOLA_VIOLATION",
    )

    # Should not crash, and should finish gracefully
    assert result is not None
    assert isinstance(result, MinimizationResult)


# ------------------------------------------------------------------------------
# 3. Live Integration Tests against Local Sample Shopping API
# ------------------------------------------------------------------------------

def test_live_sample_api_bola_verifier():
    """Test BugVerifier against the running local API on http://127.0.0.1:8000."""
    executor = RequestExecutor(base_url="http://127.0.0.1:8000")
    verifier = BugVerifier(executor=executor)

    # Run 2 clean verification replays
    result = verifier.verify_bola_scenario(repeat_count=2)

    assert result.is_reproducible is True
    assert result.status == "CONFIRMED_REPRODUCIBLE"
    assert result.successful_runs == 2
    assert result.runs_evaluated == 2
    assert len(result.findings) == 2
    assert result.findings[0].bug_type == "BOLA_VIOLATION"
    assert result.findings[1].bug_type == "BOLA_VIOLATION"


def test_live_sample_api_bola_minimizer():
    """Test TestMinimizer against the running local API on http://127.0.0.1:8000.

    Starting with a noisy 10-request BOLA sequence containing:
    - 6 redundant GET /health requests
    - 2 redundant payload fields on the order creation request
    The minimizer must:
    - Prune all 6 health requests -> 4 requests remaining (60.0% reduction).
    - Prune redundant payload fields (notes, gift_wrap).
    - Preserve the exact BOLA security vulnerability on GET /orders/{order_id}.
    """
    executor = RequestExecutor(base_url="http://127.0.0.1:8000")
    minimizer = TestMinimizer(executor=executor)

    noisy_seq = TestSequence.from_bola_scenario(with_noise=True)
    assert noisy_seq.request_count == 10

    result = minimizer.minimize_bola_scenario(starting_sequence=noisy_seq)

    # 1. Request count must be reduced from 10 to exactly 4
    assert result.is_reduced is True
    assert result.original_request_count == 10
    assert result.minimized_request_count == 4
    assert result.reduction_ratio == 0.6
    assert result.reduction_percentage == 60.0

    # 2. All 6 health checks must be pruned
    assert len(result.removed_step_names) == 6
    for name in result.removed_step_names:
        assert "health" in name.lower()

    # 3. Redundant body fields must be pruned
    assert any("notes" in f for f in result.removed_payload_fields)
    assert any("gift_wrap" in f for f in result.removed_payload_fields)

    # 4. Minimized sequence must contain only the 4 essential steps
    min_steps = result.minimized_sequence.steps
    assert len(min_steps) == 4
    assert min_steps[0].name == "Login Alice"
    assert min_steps[1].name == "Create Alice Order"
    assert min_steps[2].name == "Login Bob"
    assert min_steps[3].name == "Bob Accesses Alice Order (BOLA Probe)"

    # 5. Executing the minimized sequence must reproduce the BOLA vulnerability
    exec_res = result.minimized_sequence.execute(executor=executor, reset_state=True)
    assert exec_res.all_success is True
    probe_exec = exec_res.execution_results[-1]
    assert probe_exec.status_code == 200

    bola_finding = BOLAOracle().check_access(
        execution_result=probe_exec,
        resource_owner_id="user-alice",
        accessor_user_id="user-bob",
        resource_id=exec_res.context.get("order_id"),
    )
    assert bola_finding is not None
    assert bola_finding.bug_type == "BOLA_VIOLATION"
    assert bola_finding.is_confirmed is True
