"""Tests for Bug Diagnoser and Report Generator (Step 7).

Verifies that:
1. Bug findings are converted into reports correctly.
2. Markdown and JSON reports contain all required sections and data fields.
3. Unsupported explanations remain labeled as hypotheses and contain uncertainty tags.
4. Actionable fixes match project structure (ownership check in sample_api).
5. PowerShell / curl and pytest reproduction scripts are generated correctly and runnable.
6. Sensitive credentials (tokens, passwords) are redacted.
7. Missing API keys and LLM network failures fall back gracefully to rule-based diagnosis.
8. Active LLM responses (mocked) are parsed properly into AIDiagnosis objects.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict
import pytest
from unittest.mock import MagicMock, patch

from agent.oracles import BugFinding
from agent.verifier import VerificationResult
from agent.minimizer import MinimizationResult, TestSequence, TestSequenceStep
from agent.reporter import (
    AIDiagnosis,
    RuleBasedDiagnoser,
    LLMDiagnoser,
    BugReport,
    BugReporter,
    generate_pytest_reproduction,
    generate_powershell_curl_script,
)


@pytest.fixture
def sample_bola_finding() -> BugFinding:
    """Fixture providing a realistic BOLA finding."""
    return BugFinding(
        finding_id="finding-test-bola-123",
        bug_type="BOLA_VIOLATION",
        severity="CRITICAL",
        endpoint="/orders/{order_id}",
        method="GET",
        explanation=(
            "Broken Object Level Authorization (BOLA / OWASP API1:2023) detected: "
            "User 'user-bob' successfully accessed private resource 'ord-1' belonging to user 'user-alice'."
        ),
        expected_behavior="HTTP 403 Forbidden or HTTP 404 Not Found for non-owner access.",
        actual_response={
            "status_code": 200,
            "body": {
                "id": "ord-1",
                "user_id": "user-alice",
                "item_name": "Autonomous Drone",
                "quantity": 1,
                "total_price": 299.99,
                "status": "pending",
            },
            "headers": {
                "content-type": "application/json",
                "authorization": "[REDACTED]",
            },
        },
        evidence={
            "resource_id": "ord-1",
            "resource_owner_id": "user-alice",
            "accessor_user_id": "user-bob",
            "accessor_token": "[REDACTED]",
            "owner_token": "[REDACTED]",
        },
    )


@pytest.fixture
def sample_500_finding() -> BugFinding:
    """Fixture providing a 500 server error finding."""
    return BugFinding(
        finding_id="finding-test-500-456",
        bug_type="SERVER_ERROR_5XX",
        severity="HIGH",
        endpoint="/orders",
        method="POST",
        explanation="Endpoint crashed returning HTTP 500 Internal Server Error.",
        expected_behavior="2xx success or graceful 4xx client error response.",
        actual_response={
            "status_code": 500,
            "body": {"detail": "Internal server crash: unhandled NoneType"},
        },
        evidence={"input_payload": {"item_name": "Crash Item", "quantity": -5}},
    )


@pytest.fixture
def sample_verification() -> VerificationResult:
    """Fixture providing a confirmed verification result."""
    return VerificationResult(
        finding_id="finding-test-bola-123",
        bug_type="BOLA_VIOLATION",
        status="CONFIRMED_REPRODUCIBLE",
        is_reproducible=True,
        runs_evaluated=3,
        runs_reproduced=3,
        flakiness_score=0.0,
        reproduction_rate=1.0,
    )


@pytest.fixture
def sample_minimization() -> MinimizationResult:
    """Fixture providing a minimization result."""
    seq_orig = TestSequence.from_bola_scenario(with_noise=True)
    seq_min = TestSequence.from_bola_scenario(with_noise=False)
    return MinimizationResult(
        target_bug_type="BOLA_VIOLATION",
        original_sequence=seq_orig,
        minimized_sequence=seq_min,
        original_request_count=10,
        minimized_request_count=4,
        reduction_ratio=0.6,
        reduction_percentage=60.0,
        is_reduced=True,
        removed_step_names=["Health Ping 1", "Health Ping 2", "Health Ping 3"],
        removed_payload_fields=["Create Order.notes", "Create Order.gift_wrap"],
    )


# ------------------------------------------------------------------------------
# 1. RuleBasedDiagnoser Tests
# ------------------------------------------------------------------------------

def test_rule_based_diagnoser_bola(sample_bola_finding, sample_verification, sample_minimization):
    """Test deterministic diagnosis for BOLA violations."""
    diagnosis = RuleBasedDiagnoser.diagnose_finding(
        sample_bola_finding,
        verification=sample_verification,
        minimization=sample_minimization,
    )
    assert not diagnosis.is_ai_generated
    assert "rule_based_fallback" in diagnosis.diagnosis_source
    assert "omits object-level authorization" in diagnosis.hypothesis
    assert any("user-bob" in ev for ev in diagnosis.supporting_evidence)
    assert any("sample_api/main.py" in chk for chk in diagnosis.additional_checks)
    assert 'order["user_id"] != current_user["user_id"]' in diagnosis.suggested_fix
    assert "403_FORBIDDEN" in diagnosis.suggested_fix
    # Must label hypothesis as unverified black-box assumption
    assert any("unverified hypothesis" in unc for unc in diagnosis.uncertainties)


def test_rule_based_diagnoser_500_error(sample_500_finding):
    """Test deterministic diagnosis for 500 server crashes."""
    diagnosis = RuleBasedDiagnoser.diagnose_finding(sample_500_finding)
    assert not diagnosis.is_ai_generated
    assert "crashed or encountered an unhandled exception" in diagnosis.hypothesis
    assert "try-except" in diagnosis.suggested_fix


def test_rule_based_diagnoser_generic_schema():
    """Test deterministic diagnosis for generic schema mismatches."""
    finding = BugFinding(
        finding_id="finding-schema-1",
        bug_type="SCHEMA_MISMATCH",
        severity="MEDIUM",
        endpoint="/products",
        method="GET",
        explanation="Field 'price' expected float, got string.",
        expected_behavior="Response matching OpenAPI contract.",
        actual_response={"status_code": 200, "body": {"price": "19.99"}},
    )
    diagnosis = RuleBasedDiagnoser.diagnose_finding(finding)
    assert not diagnosis.is_ai_generated
    assert "violates its documented OpenAPI specification" in diagnosis.hypothesis
    assert "Pydantic" in diagnosis.suggested_fix


# ------------------------------------------------------------------------------
# 2. LLMDiagnoser Tests (Missing API key, Mocked API, Network Failure)
# ------------------------------------------------------------------------------

def test_llm_diagnoser_unconfigured(monkeypatch, sample_bola_finding):
    """When no API key is set, LLMDiagnoser falls back to rule-based without error."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    diagnoser = LLMDiagnoser(api_key=None)
    assert not diagnoser.is_configured
    diagnosis = diagnoser.diagnose(sample_bola_finding)
    assert not diagnosis.is_ai_generated
    assert "rule_based_fallback" in diagnosis.diagnosis_source


def test_llm_diagnoser_mocked_success(monkeypatch, sample_bola_finding):
    """When API key is provided and LLM responds, parses structured diagnosis."""
    mock_llm_response = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "hypothesis": "Hypothesis: The endpoint checks auth token validity but lacks a row-level owner check.",
                        "supporting_evidence": ["Bob accessed Alice's order ord-1", "HTTP 200 returned"],
                        "additional_checks": ["Inspect sample_api/main.py line 120", "Try requesting nonexistent order"],
                        "suggested_fix": 'if order["user_id"] != current_user["user_id"]: raise HTTPException(403)',
                        "remediation_explanation": "Ensure accessor ID matches order owner ID before serialization.",
                        "uncertainties": ["Internal database foreign key structure not examined"],
                    })
                }
            }
        ]
    }

    diagnoser = LLMDiagnoser(api_key="sk-mock-key", model="gpt-4o-mini")
    assert diagnoser.is_configured

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = mock_llm_response

    with patch("httpx.Client.post", return_value=mock_resp):
        diagnosis = diagnoser.diagnose(sample_bola_finding)

    assert diagnosis.is_ai_generated
    assert diagnosis.diagnosis_source == "gpt-4o-mini"
    assert "row-level owner check" in diagnosis.hypothesis
    assert len(diagnosis.supporting_evidence) == 2
    assert "Internal database foreign key structure" in diagnosis.uncertainties[0]


def test_llm_diagnoser_mocked_failure_fallback(monkeypatch, sample_bola_finding):
    """When LLM network request fails, gracefully fallback to rule-based diagnosis with uncertainty note."""
    diagnoser = LLMDiagnoser(api_key="sk-mock-key")
    assert diagnoser.is_configured

    with patch("httpx.Client.post", side_effect=RuntimeError("Connection timeout to LLM provider")):
        diagnosis = diagnoser.diagnose(sample_bola_finding)

    # Must fall back gracefully without raising exception
    assert not diagnosis.is_ai_generated
    assert "rule_based_fallback" in diagnosis.diagnosis_source
    assert any("LLM diagnostic call failed" in unc for unc in diagnosis.uncertainties)


# ------------------------------------------------------------------------------
# 3. BugReport and Markdown/JSON Serialization Tests
# ------------------------------------------------------------------------------

def test_bug_report_to_markdown_and_json(sample_bola_finding, sample_verification, sample_minimization, tmp_path):
    """Test that BugReport serializes correctly to Markdown, JSON, and files."""
    reporter = BugReporter()
    report = reporter.generate_report(
        finding=sample_bola_finding,
        verification=sample_verification,
        minimization=sample_minimization,
    )

    # Validate BugReport fields
    assert report.finding_id == "finding-test-bola-123"
    assert report.bug_type == "BOLA_VIOLATION"
    assert report.severity == "CRITICAL"
    assert report.verification_status == "CONFIRMED_REPRODUCIBLE"
    assert report.is_reproducible is True
    assert report.original_requests_count == 10
    assert report.minimized_requests_count == 4
    assert report.reduction_percentage == 60.0

    # Markdown export tests
    md_content = report.to_markdown()
    assert "# Security Bug Report:" in md_content
    assert "**Report ID:**" in md_content
    assert "**Classification:** `BOLA_VIOLATION`" in md_content
    assert "## 1. Executive Summary" in md_content
    assert "## 2. Root Cause Hypothesis (AI Diagnosis)" in md_content
    assert "## 3. Actionable Code Remediation" in md_content
    assert "## 4. Test Minimization & Reproduction Steps" in md_content
    assert "60.0% reduced" in md_content
    assert "## 5. Reproduction Instructions" in md_content
    assert "Option A: Windows PowerShell" in md_content
    assert "Option B: Standalone Pytest" in md_content

    # JSON export tests
    json_content = report.to_json()
    parsed_json = json.loads(json_content)
    assert parsed_json["finding_id"] == "finding-test-bola-123"
    assert parsed_json["reduction_percentage"] == 60.0
    assert "diagnosis" in parsed_json
    assert "hypothesis" in parsed_json["diagnosis"]

    # File save tests
    md_file, json_file, pytest_file = report.save_to_disk(output_dir=str(tmp_path))
    assert md_file.exists()
    assert json_file.exists()
    assert pytest_file.exists()
    assert md_file.read_text(encoding="utf-8") == md_content
    assert json_file.read_text(encoding="utf-8") == json_content


def test_sensitive_credential_redaction_in_report(tmp_path):
    """Ensure no raw tokens or passwords leak into generated reports or evidence dumps."""
    finding = BugFinding(
        finding_id="finding-leak-test",
        bug_type="BOLA_VIOLATION",
        severity="CRITICAL",
        endpoint="/orders/1",
        method="GET",
        explanation="Sensitive test",
        expected_behavior="403",
        actual_response={
            "headers": {
                "Authorization": "[REDACTED]",
                "X-Api-Key": "[REDACTED]",
            },
            "body": {"status": "ok"},
        },
        evidence={
            "token": "[REDACTED]",
            "password": "[REDACTED]",
        },
    )

    reporter = BugReporter()
    report = reporter.generate_report(finding=finding)
    md_text = report.to_markdown()
    json_text = report.to_json()

    # Raw secret tokens should not appear
    assert "secret_password_123" not in md_text
    assert "eyJh...raw_jwt_token" not in md_text
    assert "[REDACTED]" in md_text
    assert "[REDACTED]" in json_text


# ------------------------------------------------------------------------------
# 4. Reproduction Script Generators
# ------------------------------------------------------------------------------

def test_generate_powershell_curl_script(sample_bola_finding):
    """Validate generated Windows PowerShell commands."""
    script = generate_powershell_curl_script(sample_bola_finding, base_url="http://127.0.0.1:8000")
    assert "Invoke-RestMethod -Method Post -Uri \"http://127.0.0.1:8000/admin/reset\"" in script
    assert "Invoke-RestMethod -Method Post -Uri \"http://127.0.0.1:8000/auth/login\"" in script
    assert "username\":\"alice\"" in script
    assert "username\":\"bob\"" in script
    assert "Invoke-RestMethod -Method Get -Uri" in script


def test_generate_pytest_reproduction(sample_bola_finding):
    """Validate generated standalone pytest suite code."""
    code = generate_pytest_reproduction(sample_bola_finding, base_url="http://127.0.0.1:8000")
    assert "def test_reproduce_bola_vulnerability():" in code
    assert "import httpx" in code
    assert 'client.post("/admin/reset")' in code
    assert 'client.post("/auth/login", json={"username": "alice"' in code
    assert '"/orders"' in code
    assert 'client.post("/auth/login", json={"username": "bob"' in code
    assert "assert bob_access.status_code == 200" in code
    assert 'assert data["user_id"] == alice_id' in code


# ------------------------------------------------------------------------------
# 5. Live Pipeline Integration Test
# ------------------------------------------------------------------------------

def test_live_reporter_bola_pipeline():
    """Run full reporter against the live sample API at http://127.0.0.1:8000."""
    executor = RequestExecutor(base_url="http://127.0.0.1:8000")
    reporter = BugReporter(executor=executor)

    # Generate report directly from a real BOLA detection
    detector = BugDetector()
    finding, meta = detector.run_bola_test(executor=executor)
    assert finding is not None
    assert finding.bug_type == "BOLA_VIOLATION"

    report = reporter.generate_report(finding=finding)
    assert report.bug_type == "BOLA_VIOLATION"
    assert report.severity == "CRITICAL"
    assert report.is_reproducible is True
    assert "BOLA" in report.title
    assert "order[\"user_id\"] != current_user[\"user_id\"]" in report.diagnosis.suggested_fix
