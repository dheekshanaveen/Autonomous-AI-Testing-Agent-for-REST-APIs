"""Reporter module: generates structured Markdown and JSON reports."""

import json
from pathlib import Path
from typing import Dict, List
from local_agent.models import Finding, FindingStatus, ScanReport


class ScanReporter:
    """Writes comprehensive Markdown and JSON reports."""

    @classmethod
    def write_reports(
        cls, report: ScanReport, output_dir: Path
    ) -> Dict[str, Path]:
        output_dir = output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        md_path = output_dir / "scan_report.md"
        json_path = output_dir / "scan_report.json"

        # Generate Markdown
        md_content = cls.generate_markdown(report)
        md_path.write_text(md_content, encoding="utf-8")

        # Generate JSON
        json_content = report.model_dump_json(indent=2)
        json_path.write_text(json_content, encoding="utf-8")

        return {
            "markdown": md_path,
            "json": json_path,
        }

    @classmethod
    def generate_markdown(cls, report: ScanReport) -> str:
        lines: List[str] = [
            "# Local Repository Testing Agent — Scan Report",
            "",
            "## Executive Summary",
            "",
            f"- **Repository Path:** `{report.repo_path}`",
            f"- **Scan Timestamp:** `{report.scan_timestamp}`",
            f"- **Execution Duration:** `{report.scan_duration_seconds:.2f}s`",
            f"- **Detected Languages:** {', '.join(report.languages) if report.languages else 'None'}",
            f"- **Source Folder Integrity:** {'✅ 100% Untouched (Verified)' if report.source_integrity_verified else '❌ WARNING: Modifications detected'}",
            "",
            "### Metric Breakdown",
            "",
            "| Metric | Count |",
            "| --- | --- |",
            f"| Source Files Scanned | `{report.files_scanned}` |",
            f"| Code Symbols Analyzed | `{report.symbols_analyzed}` |",
            f"| Test Candidates Generated | `{report.candidates_generated}` |",
            f"| Total Tests Executed | `{report.tests_executed}` |",
            f"| **Verified Failures (Reproduced)** | **`{report.verified_failures_count}`** |",
            f"| Leads to Investigate | `{report.leads_count}` |",
            f"| Setup Gaps / Blocked | `{report.setup_gaps_count}` |",
            "",
            "---",
            "",
            f"## 1. Verified Failures ({report.verified_failures_count})",
            "",
            "> [!IMPORTANT]",
            "> A finding is **verified** only when the generated test observes the failure and an independent replay reproduces it. Each entry below includes exact inputs, observed failure, and a runnable test.",
            "",
        ]

        if not report.verified_failures:
            lines.append("No verified failures were observed.\n")
        else:
            for idx, finding in enumerate(report.verified_failures, 1):
                lines.extend(cls._format_verified_finding_md(idx, finding))

        lines.extend([
            "---",
            "",
            f"## 2. Leads to Investigate ({report.leads_count})",
            "",
            "Observations and candidate hypotheses that could not be confirmed as verified failures:",
            "",
        ])

        if not report.leads:
            lines.append("No unconfirmed leads.\n")
        else:
            for idx, lead in enumerate(report.leads, 1):
                lines.extend([
                    f"### Lead #{idx}: `{lead.symbol_name}` ({lead.category})",
                    f"- **Source Reference:** `{lead.source_reference}`",
                    f"- **Input Evaluated:** `{lead.input_summary}`",
                    f"- **Hypothesis:** {lead.expected_behavior}",
                    f"- **Reason Unconfirmed:** {lead.reason_unconfirmed or 'Did not cause unhandled failure on execution.'}",
                    "",
                ])

        lines.extend([
            "---",
            "",
            f"## 3. Setup Gaps & Untested Areas ({report.setup_gaps_count})",
            "",
            "Areas where test execution could not be completed due to environment or dependency constraints:",
            "",
        ])

        if not report.setup_gaps and not report.untested_areas:
            lines.append("No setup gaps encountered.\n")
        else:
            for idx, gap in enumerate(report.setup_gaps, 1):
                lines.extend([
                    f"### Gap #{idx}: `{gap.symbol_name}`",
                    f"- **Reference:** `{gap.source_reference}`",
                    f"- **Reason:** {gap.reason_unconfirmed or gap.observed_behavior}",
                    "",
                ])
            for area in report.untested_areas:
                lines.append(f"- {area}")
            lines.append("")

        lines.extend([
            "---",
            "",
            "## 4. Source Folder Immutability Guarantee",
            "",
            "The selected local repository was monitored with pre- and post-scan SHA-256 checksums.",
            f"- **Status:** {'PASSED — Original files remain completely unchanged.' if report.source_integrity_verified else 'FAILED — Differences detected.'}",
            "- All generated tests and reports are located strictly in the external output directory.",
            "",
        ])

        return "\n".join(lines)

    @classmethod
    def _format_verified_finding_md(cls, idx: int, finding: Finding) -> List[str]:
        test_path_str = finding.test_file_path or "N/A"
        return [
            f"### Finding #{idx} (`{finding.id}`): {finding.observed_behavior.splitlines()[0]}",
            "",
            f"- **Target Symbol:** `{finding.symbol_name}`",
            f"- **Source Reference:** `{finding.source_reference}`",
            f"- **Defect Category:** `{finding.category}`",
            f"- **Exact Inputs:** `{finding.input_summary}`",
            f"- **Expected Behavior:** {finding.expected_behavior}",
            f"- **Observed Behavior:** {finding.observed_behavior}",
            f"- **Standalone Test File:** `{test_path_str}`",
            f"- **Replay Command:**",
            f"  ```bash",
            f"  {finding.replay_command}",
            f"  ```",
            "",
            "#### Execution Evidence (Replay Output)",
            "```text",
            (finding.execution_evidence.strip() or "No traceback output recorded."),
            "```",
            "",
        ]

