"""Tests for reporter module."""

import json
from pathlib import Path
from local_agent.agent_core import TestingAgent
from local_agent.reporter import ScanReporter


def test_reporter_generates_md_and_json(sample_python_repo_path, temp_dir):
    agent = TestingAgent(timeout_seconds=5.0)
    report = agent.scan(str(sample_python_repo_path), output_dir=str(temp_dir))

    md_path = temp_dir / "scan_report.md"
    json_path = temp_dir / "scan_report.json"

    assert md_path.exists()
    assert json_path.exists()

    md_content = md_path.read_text(encoding="utf-8")
    assert "# Local Repository Testing Agent — Scan Report" in md_content
    assert "Verified Failures" in md_content
    assert "Source Folder Immutability Guarantee" in md_content

    json_data = json.loads(json_path.read_text(encoding="utf-8"))
    assert json_data["repo_path"] == str(sample_python_repo_path.resolve())
    assert json_data["source_integrity_verified"] is True
    assert "verified_failures" in json_data

