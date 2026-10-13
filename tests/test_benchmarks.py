"""Automated Tests for Benchmark Evaluator and Comparison Engine (Step 8).

Verifies that:
1. AgentEvaluationResult and SchemathesisEvaluationResult models record expected fields.
2. Benchmark comparison reports correctly format CSV, JSON, and Markdown summaries.
3. Schemathesis baseline run records test case counts and status codes.
4. Saving results to disk generates valid, readable benchmark files.
5. Live benchmark evaluation against the sample API executes without errors.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import pytest

from benchmarks.evaluator import (
    AgentEvaluationResult,
    SchemathesisEvaluationResult,
    BenchmarkComparisonReport,
    BenchmarkEvaluator,
)
from agent.executor import RequestExecutor


@pytest.fixture
def mock_agent_result() -> AgentEvaluationResult:
    """Fixture providing simulated Agent evaluation metrics."""
    return AgentEvaluationResult(
        target_url="http://127.0.0.1:8000",
        duration_seconds=42.50,
        total_http_requests=45,
        tests_generated=10,
        tests_passed=10,
        tests_failed=0,
        bugs_detected=1,
        true_positives=1,
        false_positives=0,
        detected_bug_types=["BOLA_VIOLATION"],
        is_verified_reproducible=True,
        minimization_original_requests=10,
        minimization_reduced_requests=4,
        minimization_reduction_percentage=60.0,
        report_generated=True,
        standalone_reproduction_runnable=True,
        llm_calls_count=0,
        llm_cost_usd=0.0,
        diagnosis_source="rule_based_fallback",
    )


@pytest.fixture
def mock_schemathesis_result() -> SchemathesisEvaluationResult:
    """Fixture providing simulated Schemathesis evaluation metrics."""
    return SchemathesisEvaluationResult(
        target_url="http://127.0.0.1:8000",
        duration_seconds=2.15,
        total_http_requests=6,
        tests_generated=6,
        tests_passed=6,
        tests_failed=0,
        server_crashes_5xx=0,
        schema_violations=0,
        bola_vulnerabilities_detected=0,
        can_detect_cross_user_bola=False,
        reasons_bola_missed=["Lacks multi-user authorization oracle"],
    )


def test_benchmark_models_serialization(mock_agent_result, mock_schemathesis_result):
    """Test model validation and JSON serialization."""
    comp = BenchmarkComparisonReport(
        target_url="http://127.0.0.1:8000",
        agent_result=mock_agent_result,
        schemathesis_result=mock_schemathesis_result,
        comparison_summary={"test_key": "test_val"},
    )
    json_str = comp.model_dump_json()
    parsed = json.loads(json_str)

    assert parsed["agent_result"]["bugs_detected"] == 1
    assert parsed["schemathesis_result"]["bola_vulnerabilities_detected"] == 0
    assert parsed["agent_result"]["minimization_reduction_percentage"] == 60.0


def test_benchmark_save_results(mock_agent_result, mock_schemathesis_result, tmp_path):
    """Test saving benchmark outcomes to JSON, CSV, and Markdown files."""
    comp = BenchmarkComparisonReport(
        target_url="http://127.0.0.1:8000",
        agent_result=mock_agent_result,
        schemathesis_result=mock_schemathesis_result,
        comparison_summary={"key_distinction": "Test distinction note"},
    )

    evaluator = BenchmarkEvaluator(output_dir=str(tmp_path))
    json_path, csv_path, md_path = evaluator._save_results(comp)

    # 1. Verify JSON file
    assert json_path.exists()
    json_data = json.loads(json_path.read_text(encoding="utf-8"))
    assert json_data["agent_result"]["true_positives"] == 1

    # 2. Verify CSV file
    assert csv_path.exists()
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = list(csv.reader(f))
        headers = reader[0]
        assert "Autonomous AI Testing Agent" in headers
        assert "Schemathesis (Baseline Fuzzer)" in headers
        # Check BOLA row
        bola_row = next(r for r in reader if r[0] == "BOLA Vulnerabilities Found")
        assert bola_row[1] == "1"
        assert bola_row[2] == "0"

    # 3. Verify Markdown file
    assert md_path.exists()
    md_text = md_path.read_text(encoding="utf-8")
    assert "# Empirical Benchmark & Tool Comparison Report" in md_text
    assert "| **BOLA (OWASP API1) Detected** |" in md_text
    assert "## 3. Detailed Tool Analysis" in md_text
    assert "## 4. Threats to Validity & Limitations" in md_text


def test_live_schemathesis_evaluation():
    """Run live Schemathesis baseline against local sample API."""
    evaluator = BenchmarkEvaluator(base_url="http://127.0.0.1:8000")
    result = evaluator.evaluate_schemathesis(max_cases_per_op=2)

    assert result.tool_name.startswith("Schemathesis")
    assert result.total_http_requests > 0
    assert result.server_crashes_5xx == 0
    assert result.bola_vulnerabilities_detected == 0
    assert result.can_detect_cross_user_bola is False
    assert len(result.reasons_bola_missed) > 0
