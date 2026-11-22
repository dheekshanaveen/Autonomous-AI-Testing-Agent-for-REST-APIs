"""Command Line Interface for Local Repository Testing Agent."""

import argparse
import json
import sys
from pathlib import Path

from local_agent.agent_core import TestingAgent
from local_agent.intake import IntakeError, validate_repository_folder
from local_agent.inventory import build_project_inventory
from local_agent.runner import IsolatedRunner


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="local_agent",
        description="Local Repository Testing Agent: scans local repos, finds edge cases, verifies reproducible failures.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: scan
    scan_parser = subparsers.add_parser("scan", help="Scan a local repository folder and generate verified findings.")
    scan_parser.add_argument("repo_path", type=str, help="Path to local repository folder.")
    scan_parser.add_argument("--output", "-o", type=str, default=None, help="Output directory for reports and tests.")
    scan_parser.add_argument("--timeout", "-t", type=float, default=5.0, help="Per-test timeout in seconds.")
    scan_parser.add_argument("--verify-fix", type=str, default=None, help="Path to corrected/fixed repository revision.")

    # Subcommand: inventory
    inv_parser = subparsers.add_parser("inventory", help="Inspect and display project structure, languages, and symbols.")
    inv_parser.add_argument("repo_path", type=str, help="Path to local repository folder.")

    # Subcommand: replay
    replay_parser = subparsers.add_parser("replay", help="Replay a generated regression test against a repository.")
    replay_parser.add_argument("test_file", type=str, help="Path to generated test file.")
    replay_parser.add_argument("repo_path", type=str, help="Path to target repository.")
    replay_parser.add_argument("--language", "-l", type=str, choices=["python", "javascript", "typescript"], default="python")

    args = parser.parse_args()

    try:
        agent = TestingAgent(timeout_seconds=getattr(args, "timeout", 5.0))

        if args.command == "scan":
            print(f"[*] Scanning local repository: {args.repo_path}")
            report = agent.scan(args.repo_path, output_dir=args.output)

            print("\n================ SCAN SUMMARY ================")
            print(f"Repository:               {report.repo_path}")
            print(f"Languages:                {', '.join(report.languages)}")
            print(f"Files scanned:            {report.files_scanned}")
            print(f"Symbols analyzed:         {report.symbols_analyzed}")
            print(f"Candidates generated:     {report.candidates_generated}")
            print(f"Tests executed:           {report.tests_executed}")
            print(f"Verified Failures:        {report.verified_failures_count}")
            print(f"Leads to investigate:     {report.leads_count}")
            print(f"Setup gaps:               {report.setup_gaps_count}")
            print(f"Folder untouched:         {'YES (Verified)' if report.source_integrity_verified else 'NO (Diff detected)'}")
            print(f"Scan duration:            {report.scan_duration_seconds:.2f}s")
            print("==============================================")

            if report.verified_failures:
                print("\n[!] VERIFIED FAILURES FOUND:")
                for finding in report.verified_failures:
                    print(f"  - [{finding.id}] {finding.symbol_name} ({finding.category})")
                    print(f"    Observed: {finding.observed_behavior}")
                    print(f"    Test:     {finding.test_file_path}")
                    print(f"    Replay:   {finding.replay_command}")

            if args.verify_fix:
                print(f"\n[*] Cross-verifying fixes on: {args.verify_fix}")
                fix_res = agent.verify_fix(args.repo_path, args.verify_fix, output_dir=args.output)
                print(f"  Fixed: {fix_res['total_verified_fixes']}/{fix_res['total_verified_failures']} verified failures resolved.")
                print(f"  All fixes confirmed: {'YES' if fix_res['all_fixes_confirmed'] else 'NO'}")

            return 0

        elif args.command == "inventory":
            source = validate_repository_folder(args.repo_path)
            inv = build_project_inventory(source)
            print(f"Repository: {inv.repo_path}")
            print(f"Languages:  {inv.languages}")
            print(f"Manifests:  {inv.manifests}")
            print(f"Files ({len(inv.source_files)}): {inv.source_files}")
            print(f"Symbols ({len(inv.symbols)}):")
            for s in inv.symbols:
                print(f"  - [{s.language}] {s.kind} {s.name} ({s.file_path}:{s.line_number}) | risks: {s.risk_flags}")
            return 0

        elif args.command == "replay":
            runner = IsolatedRunner()
            test_file = Path(args.test_file)
            repo_root = Path(args.repo_path)
            res = runner.run_test(test_file, args.language, repo_root)
            print(f"Replay result: {'PASS' if res.passed else 'FAIL'}")
            print(f"Exit code:     {res.exit_code}")
            print(f"Duration:      {res.duration_seconds}s")
            if res.failure_type:
                print(f"Failure:       {res.failure_type}: {res.error_message}")
            if res.stdout:
                print("--- stdout ---")
                print(res.stdout)
            if res.stderr:
                print("--- stderr ---")
                print(res.stderr)
            return 0 if res.passed else 1

    except IntakeError as ie:
        print(f"Error: {ie}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

