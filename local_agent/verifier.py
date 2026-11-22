"""Verifier module: performs 2-phase replay verification, classifies findings, and verifies fixes."""

import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from local_agent.models import ExecutionResult, Finding, FindingStatus, TestCandidate
from local_agent.runner import IsolatedRunner


class FindingVerifier:
    """Verifies failures via deterministic replay and classifies outcomes."""

    def __init__(self, runner: IsolatedRunner):
        self.runner = runner

    def verify_candidate(
        self,
        candidate: TestCandidate,
        test_file: Path,
        repo_root: Path,
    ) -> Finding:
        finding_id = f"finding-{uuid.uuid4().hex[:8]}"

        # Phase 1: Initial Execution
        run1 = self.runner.run_test(test_file, candidate.language, repo_root)

        # Generate replay command for reproducing
        if candidate.language == "python":
            replay_cmd = f"pytest {test_file.as_posix()} -v"
        else:
            replay_cmd = f"node --test {test_file.as_posix()}"

        source_ref = f"{candidate.file_path} :: {candidate.symbol_name}"
        input_summary = str(candidate.inputs) if candidate.inputs else "State sequence execution"

        # If run 1 passed:
        if run1.passed:
            return Finding(
                id=finding_id,
                status=FindingStatus.PASSED_EXPECTED,
                category=candidate.category,
                symbol_name=candidate.symbol_name,
                file_path=candidate.file_path,
                line_number=1,
                language=candidate.language,
                input_summary=input_summary,
                expected_behavior=candidate.expected_behavior,
                observed_behavior="Execution succeeded as expected (no defect observed).",
                source_reference=source_ref,
                execution_evidence=run1.stdout or run1.stderr,
                test_file_path=str(test_file.resolve()),
                replay_command=replay_cmd,
                run1_result=run1,
            )

        # Check for setup gaps (missing modules, libraries, etc.)
        if run1.failure_type and run1.failure_type.startswith("SetupGap:"):
            return Finding(
                id=finding_id,
                status=FindingStatus.SETUP_GAP,
                category=candidate.category,
                symbol_name=candidate.symbol_name,
                file_path=candidate.file_path,
                line_number=1,
                language=candidate.language,
                input_summary=input_summary,
                expected_behavior=candidate.expected_behavior,
                observed_behavior=f"Setup failure: {run1.error_message}",
                source_reference=source_ref,
                execution_evidence=run1.stderr or run1.stdout,
                test_file_path=str(test_file.resolve()),
                replay_command=replay_cmd,
                reason_unconfirmed=f"Environment setup incomplete: {run1.error_message}",
                run1_result=run1,
            )

        # Phase 2: Deterministic Replay
        run2 = self.runner.run_test(test_file, candidate.language, repo_root)

        if not run2.passed:
            # Verified failure: observed and independently reproduced!
            observed = f"{run2.failure_type}: {run2.error_message}" if run2.error_message else (run2.failure_type or "Test failed")
            evidence = run2.stderr or run2.stdout

            return Finding(
                id=finding_id,
                status=FindingStatus.VERIFIED_FAILURE,
                category=candidate.category,
                symbol_name=candidate.symbol_name,
                file_path=candidate.file_path,
                line_number=1,
                language=candidate.language,
                input_summary=input_summary,
                expected_behavior=candidate.expected_behavior,
                observed_behavior=observed,
                source_reference=source_ref,
                execution_evidence=evidence,
                test_file_path=str(test_file.resolve()),
                replay_command=replay_cmd,
                run1_result=run1,
                run2_replay_result=run2,
            )
        else:
            # Flaky: failed on run 1, but passed on replay
            return Finding(
                id=finding_id,
                status=FindingStatus.LEAD,
                category=candidate.category,
                symbol_name=candidate.symbol_name,
                file_path=candidate.file_path,
                line_number=1,
                language=candidate.language,
                input_summary=input_summary,
                expected_behavior=candidate.expected_behavior,
                observed_behavior=f"Initial failure ({run1.failure_type}) could not be reproduced on replay.",
                source_reference=source_ref,
                execution_evidence=run1.stderr or run1.stdout,
                test_file_path=str(test_file.resolve()),
                replay_command=replay_cmd,
                reason_unconfirmed="Non-deterministic behavior: test passed on replay.",
                run1_result=run1,
                run2_replay_result=run2,
            )

    def verify_fix(
        self,
        test_file: Path,
        language: str,
        faulty_repo: Path,
        fixed_repo: Path,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Verify that a test exposes defect on faulty repo (fails)
        and passes on fixed repo (succeeds).
        """
        # Run on faulty repo
        faulty_res = self.runner.run_test(test_file, language, faulty_repo)
        # Run on fixed repo
        fixed_res = self.runner.run_test(test_file, language, fixed_repo)

        is_verified_fix = (not faulty_res.passed) and fixed_res.passed

        details = {
            "faulty_passed": faulty_res.passed,
            "faulty_failure": faulty_res.failure_type,
            "faulty_error": faulty_res.error_message,
            "fixed_passed": fixed_res.passed,
            "verified_fix": is_verified_fix,
        }
        return is_verified_fix, details

