"""Bug Verifier for Autonomous AI Testing Agent for REST APIs.

Verifies whether detected anomalies and security vulnerabilities are real,
consistently reproducible defects rather than transient or flaky glitches.
Repeats test executions from a clean, reset state at least twice.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from agent.executor import ExecutionResult, RequestExecutor
from agent.oracles import BugFinding, BOLAOracle, BugDetector

logger = logging.getLogger("agent.verifier")


# ------------------------------------------------------------------------------
# Verification Result Models
# ------------------------------------------------------------------------------

class VerificationResult(BaseModel):
    """Structured outcome of a bug reproducibility evaluation."""

    __test__ = False  # Prevent pytest from collecting this class as a test suite

    verification_id: str = Field(default_factory=lambda: f"verif-{uuid.uuid4().hex[:8]}")
    bug_type: str = Field(..., description="Target bug classification being verified")
    status: str = Field(
        ...,
        description="'CONFIRMED_REPRODUCIBLE', 'FLAKY', or 'NOT_REPRODUCIBLE'",
    )
    is_reproducible: bool = Field(
        ...,
        description="True if the defect reproduced across all verification runs",
    )
    runs_evaluated: int = Field(default=2, description="Number of verification runs executed")
    successful_runs: int = Field(default=0, description="Runs in which the bug was reproduced")
    failed_runs: int = Field(default=0, description="Runs in which the bug failed to reproduce")
    details: str = Field(default="", description="Detailed human-readable explanation")
    findings: List[Optional[BugFinding]] = Field(
        default_factory=list,
        description="Bug findings captured during verification runs",
    )

    def summary(self) -> str:
        """One-line summary of verification result."""
        tag = "REPRODUCIBLE" if self.is_reproducible else self.status
        return (
            f"[{tag}] Bug '{self.bug_type}': {self.successful_runs}/{self.runs_evaluated} "
            f"runs reproduced the defect."
        )

    def format_report(self) -> str:
        """Multi-line ASCII formatted report card."""
        status_tag = "CONFIRMED REPRODUCIBLE" if self.is_reproducible else self.status
        lines = [
            "=" * 76,
            f"BUG VERIFICATION REPORT: {self.verification_id} [{status_tag}]",
            "=" * 76,
            f"Bug Type:        {self.bug_type}",
            f"Reproducible:    {'Yes' if self.is_reproducible else 'No'}",
            f"Runs Evaluated:  {self.runs_evaluated}",
            f"Success Rate:    {self.successful_runs}/{self.runs_evaluated} runs",
            "-" * 76,
            "DETAILS:",
            f"  {self.details}",
            "=" * 76,
        ]
        return "\n".join(lines)


# ------------------------------------------------------------------------------
# Bug Verifier Implementation
# ------------------------------------------------------------------------------

class BugVerifier:
    """Verifies that API defects reproduce consistently across clean test runs."""

    __test__ = False

    def __init__(self, executor: Optional[RequestExecutor] = None):
        self.executor = executor or RequestExecutor(base_url="http://127.0.0.1:8000")

    def reset_target_state(self) -> bool:
        """Reset the test target's state to ensure clean starting conditions."""
        try:
            res = self.executor.post("/admin/reset")
            return res.is_success
        except Exception as exc:
            logger.warning("Failed to reset test target state: %s", exc)
            return False

    def verify_bola_scenario(
        self,
        repeat_count: int = 2,
        alice_user: str = "alice",
        alice_pass: str = "alice123",
        bob_user: str = "bob",
        bob_pass: str = "bob123",
    ) -> VerificationResult:
        """Verify the Broken Object Level Authorization (BOLA) vulnerability.

        Executes the complete cross-user test sequence from a clean state
        at least `repeat_count` times (default: 2).
        """
        if repeat_count < 2:
            repeat_count = 2

        successful_runs = 0
        captured_findings: List[Optional[BugFinding]] = []
        oracle = BOLAOracle()

        for run_idx in range(1, repeat_count + 1):
            logger.info("Running BOLA verification iteration %d/%d...", run_idx, repeat_count)
            # 1. Reset state before each iteration
            self.reset_target_state()

            try:
                finding, meta = oracle.test_sample_api_orders_bola(
                    executor=self.executor,
                    alice_user=alice_user,
                    alice_pass=alice_pass,
                    bob_user=bob_user,
                    bob_pass=bob_pass,
                )
            except Exception as exc:
                logger.warning("BOLA verification iteration %d failed with error: %s", run_idx, exc)
                finding = None

            captured_findings.append(finding)
            if finding is not None and finding.bug_type == "BOLA_VIOLATION" and finding.is_confirmed:
                successful_runs += 1

        failed_runs = repeat_count - successful_runs

        # Determine reproducibility status
        if successful_runs == repeat_count:
            status = "CONFIRMED_REPRODUCIBLE"
            is_reproducible = True
            details = (
                f"The BOLA vulnerability on GET /orders/{{order_id}} was successfully "
                f"reproduced in {successful_runs}/{repeat_count} clean test runs."
            )
        elif successful_runs > 0:
            status = "FLAKY"
            is_reproducible = False
            details = (
                f"Inconsistent behavior detected: BOLA occurred in {successful_runs}/{repeat_count} runs. "
                "The result is flagged as inconclusive/flaky."
            )
        else:
            status = "NOT_REPRODUCIBLE"
            is_reproducible = False
            details = (
                f"The vulnerability could not be reproduced ({successful_runs}/{repeat_count} runs). "
                "The issue may be transient or resolved."
            )

        return VerificationResult(
            bug_type="BOLA_VIOLATION",
            status=status,
            is_reproducible=is_reproducible,
            runs_evaluated=repeat_count,
            successful_runs=successful_runs,
            failed_runs=failed_runs,
            details=details,
            findings=captured_findings,
        )

    def verify_evaluator(
        self,
        evaluator_fn: Callable[[], Tuple[bool, Optional[BugFinding]]],
        bug_type: str,
        repeat_count: int = 2,
    ) -> VerificationResult:
        """Generic verification helper that replays an evaluation function.

        Args:
            evaluator_fn: Callable that runs a clean test iteration and returns
                          (is_reproduced: bool, finding: Optional[BugFinding]).
            bug_type: Classification string of the target bug.
            repeat_count: Minimum number of clean replays to evaluate (>= 2).
        """
        if repeat_count < 2:
            repeat_count = 2

        successful_runs = 0
        captured_findings: List[Optional[BugFinding]] = []

        for run_idx in range(1, repeat_count + 1):
            self.reset_target_state()
            try:
                reproduced, finding = evaluator_fn()
            except Exception as exc:
                logger.warning("Verification run %d encountered exception: %s", run_idx, exc)
                reproduced, finding = False, None

            captured_findings.append(finding)
            if reproduced:
                successful_runs += 1

        failed_runs = repeat_count - successful_runs

        if successful_runs == repeat_count:
            status = "CONFIRMED_REPRODUCIBLE"
            is_reproducible = True
            details = f"Bug '{bug_type}' reproduced consistently across {successful_runs}/{repeat_count} clean runs."
        elif successful_runs > 0:
            status = "FLAKY"
            is_reproducible = False
            details = f"Bug '{bug_type}' was inconsistent ({successful_runs}/{repeat_count} runs reproduced). Flagged as flaky."
        else:
            status = "NOT_REPRODUCIBLE"
            is_reproducible = False
            details = f"Bug '{bug_type}' failed to reproduce ({successful_runs}/{repeat_count} runs)."

        return VerificationResult(
            bug_type=bug_type,
            status=status,
            is_reproducible=is_reproducible,
            runs_evaluated=repeat_count,
            successful_runs=successful_runs,
            failed_runs=failed_runs,
            details=details,
            findings=captured_findings,
        )


if __name__ == "__main__":
    import sys

    target_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    print(f"[*] Running Bug Verifier against: {target_url}")

    cli_executor = RequestExecutor(base_url=target_url)
    verifier = BugVerifier(executor=cli_executor)

    print("[*] Replaying BOLA security test twice from a clean starting state...")
    result = verifier.verify_bola_scenario(repeat_count=2)

    print("\n" + result.format_report() + "\n")
