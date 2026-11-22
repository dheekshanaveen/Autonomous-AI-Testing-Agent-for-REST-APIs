"""Agent Core: orchestrates intake, inventory, analysis, generation, execution, replay, and reporting."""

import datetime
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from local_agent.analyzer import TestCandidateAnalyzer
from local_agent.generator import TestGenerator
from local_agent.intake import ProjectSource, validate_repository_folder
from local_agent.inventory import build_project_inventory
from local_agent.models import Finding, FindingStatus, ScanReport
from local_agent.reporter import ScanReporter
from local_agent.runner import IsolatedRunner
from local_agent.verifier import FindingVerifier


class TestingAgent:
    """Orchestrates the entire local repository testing workflow."""

    __test__ = False

    def __init__(
        self,
        timeout_seconds: float = 5.0,
        python_executable: Optional[str] = None,
    ):
        self.timeout_seconds = timeout_seconds
        self.runner = IsolatedRunner(
            timeout_seconds=timeout_seconds,
            python_executable=python_executable,
        )
        self.verifier = FindingVerifier(self.runner)

    def scan(
        self,
        repo_path: str,
        output_dir: Optional[str] = None,
    ) -> ScanReport:
        start_time = time.perf_counter()
        scan_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # 1. Intake & Validation
        source: ProjectSource = validate_repository_folder(repo_path)
        repo_root = source.root_path

        # Determine output directory (default: <repo_root>/../scan_output_<name>)
        if output_dir:
            out_path = Path(output_dir).resolve()
        else:
            out_path = repo_root.parent / f"scan_output_{repo_root.name}"
        out_path.mkdir(parents=True, exist_ok=True)

        # 2. Inventory
        inventory = build_project_inventory(source)

        # 3. Candidate Analysis
        candidates = TestCandidateAnalyzer.analyze(inventory)

        # 4. Test Generation, Execution & Replay
        verified_failures: List[Finding] = []
        leads: List[Finding] = []
        setup_gaps: List[Finding] = []
        tests_executed = 0

        for candidate in candidates:
            try:
                test_file = TestGenerator.generate_test(candidate, out_path, repo_root)
                finding = self.verifier.verify_candidate(candidate, test_file, repo_root)
                tests_executed += 1

                if finding.status == FindingStatus.VERIFIED_FAILURE:
                    verified_failures.append(finding)
                elif finding.status == FindingStatus.LEAD:
                    leads.append(finding)
                elif finding.status == FindingStatus.SETUP_GAP:
                    setup_gaps.append(finding)
                # PASSED_EXPECTED is counted in tests_executed but not flagged as an issue

            except Exception as e:
                leads.append(
                    Finding(
                        id=f"err-{candidate.id}",
                        status=FindingStatus.LEAD,
                        category=candidate.category,
                        symbol_name=candidate.symbol_name,
                        file_path=candidate.file_path,
                        line_number=1,
                        language=candidate.language,
                        input_summary=str(candidate.inputs),
                        expected_behavior=candidate.expected_behavior,
                        observed_behavior=f"Test pipeline generation error: {e}",
                        source_reference=f"{candidate.file_path} :: {candidate.symbol_name}",
                        execution_evidence=str(e),
                        reason_unconfirmed=f"Internal generator exception: {e}",
                    )
                )

        # 5. Check Source Folder Immutability
        is_unchanged, diffs = source.verify_unchanged()

        duration = time.perf_counter() - start_time

        # 6. Build Scan Report
        report = ScanReport(
            repo_path=str(repo_root),
            scan_timestamp=scan_timestamp,
            scan_duration_seconds=round(duration, 2),
            languages=inventory.languages,
            files_scanned=len(inventory.source_files),
            symbols_analyzed=len(inventory.symbols),
            candidates_generated=len(candidates),
            tests_executed=tests_executed,
            verified_failures_count=len(verified_failures),
            leads_count=len(leads),
            setup_gaps_count=len(setup_gaps),
            source_integrity_verified=is_unchanged,
            verified_failures=verified_failures,
            leads=leads,
            setup_gaps=setup_gaps,
            untested_areas=inventory.setup_notes + ([f"Integrity alert: {d}" for d in diffs] if not is_unchanged else []),
        )

        # 7. Write Reports to Disk
        ScanReporter.write_reports(report, out_path)

        return report

    def verify_fix(
        self,
        faulty_repo_path: str,
        fixed_repo_path: str,
        output_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Verify that defects exposed in faulty repo are resolved in fixed repo."""
        scan_faulty = self.scan(faulty_repo_path, output_dir=output_dir)
        fixed_source = validate_repository_folder(fixed_repo_path)

        fix_results: List[Dict[str, Any]] = []

        for finding in scan_faulty.verified_failures:
            if not finding.test_file_path:
                continue
            test_file = Path(finding.test_file_path)
            is_fixed, details = self.verifier.verify_fix(
                test_file=test_file,
                language=finding.language,
                faulty_repo=Path(faulty_repo_path).resolve(),
                fixed_repo=fixed_source.root_path,
            )
            fix_results.append({
                "finding_id": finding.id,
                "symbol_name": finding.symbol_name,
                "verified_fix": is_fixed,
                "details": details,
            })

        all_fixed = all(r["verified_fix"] for r in fix_results) if fix_results else False
        return {
            "faulty_repo": faulty_repo_path,
            "fixed_repo": fixed_repo_path,
            "total_verified_failures": len(scan_faulty.verified_failures),
            "total_verified_fixes": sum(1 for r in fix_results if r["verified_fix"]),
            "all_fixes_confirmed": all_fixed,
            "results": fix_results,
        }

