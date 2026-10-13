"""Automated Tests for Bug Detection Oracles (Step 5).

Verifies:
1. ServerErrorOracle flags HTTP 5xx errors as possible bugs without crashes.
2. SchemaConformanceOracle flags schema violations (types, missing fields, undocumented status codes).
3. SchemaConformanceOracle does not falsely flag conforming responses.
4. BOLAOracle flags unauthorized cross-user resource access as critical confirmed bug.
5. BOLAOracle does not flag authorized owner access.
6. Non-documented endpoints or responses are handled without inventing rules.
7. Sensitive credentials (passwords, tokens, Authorization headers) are strictly redacted in findings.
8. End-to-end integration against the running local Sample Shopping API.
"""

from __future__ import annotations

import json
from typing import Any, Dict
import pytest

from agent.executor import ExecutionResult, RequestTrace, ResponseTrace, RequestExecutor
from agent.spec_reader import OpenAPISpecReader
from agent.oracles import (
    BugFinding,
    ServerErrorOracle,
    SchemaConformanceOracle,
    BOLAOracle,
    BugDetector,
)


# ------------------------------------------------------------------------------
# Helpers & Fixtures
# ------------------------------------------------------------------------------

SAMPLE_SPEC_DICT = {
    "openapi": "3.1.0",
    "info": {"title": "Test Shop API", "version": "1.0.0"},
    "paths": {
        "/orders/{order_id}": {
            "get": {
                "summary": "Get order by ID",
                "responses": {
                    "200": {
                        "description": "Successful Response",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["id", "user_id", "total_price"],
                                    "properties": {
                                        "id": {"type": "string"},
                                        "user_id": {"type": "string"},
                                        "total_price": {"type": "number"},
                                        "status": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "404": {
                        "description": "Not Found",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"detail": {"type": "string"}},
                                }
                            }
                        },
                    },
                },
            }
        },
        "/health": {
            "get": {
                "summary": "Health check",
                "responses": {
                    "200": {
                        "description": "OK",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["status"],
                                    "properties": {"status": {"type": "string"}},
                                }
                            }
                        },
                    }
                },
            }
        },
    },
}


@pytest.fixture
def sample_spec():
    return OpenAPISpecReader.load(SAMPLE_SPEC_DICT)


def make_execution_result(
    method: str = "GET",
    url: str = "http://127.0.0.1:8000/orders/ord-1",
    path_template: str = "/orders/{order_id}",
    headers: Dict[str, str] = None,
    req_body: Any = None,
    status_code: int = 200,
    resp_body: Any = None,
    is_json: bool = True,
    resp_headers: Dict[str, str] = None,
) -> ExecutionResult:
    """Construct an ExecutionResult for testing oracles."""
    req_trace = RequestTrace(
        method=method,
        url=url,
        path_template=path_template,
        headers=headers or {},
        body=req_body,
    )
    resp_trace = ResponseTrace(
        status_code=status_code,
        headers=resp_headers or {"content-type": "application/json"},
        body=resp_body,
        is_json=is_json,
        text=json.dumps(resp_body) if (resp_body and is_json) else str(resp_body or ""),
    )
    return ExecutionResult(request=req_trace, response=resp_trace, duration_ms=15.0)


# ------------------------------------------------------------------------------
# Check 1: Server Error Oracle Tests
# ------------------------------------------------------------------------------

def test_server_error_oracle_detects_http_500():
    """Verify HTTP 500 triggers a high-severity possible bug finding."""
    oracle = ServerErrorOracle()
    exec_res = make_execution_result(
        status_code=500,
        resp_body={"detail": "Internal Server Error in database pool"},
    )

    finding = oracle.check(exec_res)
    assert finding is not None
    assert finding.bug_type == "SERVER_ERROR_5XX"
    assert finding.severity == "HIGH"
    assert finding.is_confirmed is False  # Must be possible/suspicious, not auto-confirmed
    assert "500" in finding.explanation


def test_server_error_oracle_detects_http_503():
    """Verify HTTP 503 Service Unavailable triggers a finding."""
    oracle = ServerErrorOracle()
    exec_res = make_execution_result(status_code=503, resp_body="Service Unavailable", is_json=False)

    finding = oracle.check(exec_res)
    assert finding is not None
    assert finding.bug_type == "SERVER_ERROR_5XX"
    assert finding.is_confirmed is False


def test_server_error_oracle_ignores_non_5xx():
    """Verify 200, 400, 404 responses are NOT flagged by ServerErrorOracle."""
    oracle = ServerErrorOracle()

    assert oracle.check(make_execution_result(status_code=200)) is None
    assert oracle.check(make_execution_result(status_code=400)) is None
    assert oracle.check(make_execution_result(status_code=404)) is None


# ------------------------------------------------------------------------------
# Check 2: Schema Conformance Oracle Tests
# ------------------------------------------------------------------------------

def test_schema_conformance_detects_type_mismatch(sample_spec):
    """Verify price returned as string instead of number is flagged as schema violation."""
    oracle = SchemaConformanceOracle(spec=sample_spec)

    # total_price is documented as 'number', but API returns string '99.99'
    invalid_body = {
        "id": "ord-1",
        "user_id": "user-alice",
        "total_price": "99.99",  # String instead of number
    }
    exec_res = make_execution_result(
        method="GET",
        path_template="/orders/{order_id}",
        status_code=200,
        resp_body=invalid_body,
    )

    findings = oracle.check(exec_res)
    assert len(findings) == 1
    f = findings[0]
    assert f.bug_type == "SCHEMA_MISMATCH"
    assert f.is_confirmed is True
    assert "total_price" in f.explanation
    assert "is not of type 'number'" in f.explanation


def test_schema_conformance_detects_missing_required_property(sample_spec):
    """Verify missing required property 'total_price' is flagged."""
    oracle = SchemaConformanceOracle(spec=sample_spec)

    # Missing total_price
    invalid_body = {"id": "ord-1", "user_id": "user-alice"}
    exec_res = make_execution_result(
        method="GET",
        path_template="/orders/{order_id}",
        status_code=200,
        resp_body=invalid_body,
    )

    findings = oracle.check(exec_res)
    assert len(findings) == 1
    f = findings[0]
    assert f.bug_type == "SCHEMA_MISMATCH"
    assert "total_price" in f.explanation
    assert "required property" in f.explanation


def test_schema_conformance_detects_undocumented_status_code(sample_spec):
    """Verify status code not documented in the specification is flagged."""
    oracle = SchemaConformanceOracle(spec=sample_spec)

    # Spec only documents 200 and 404 for GET /orders/{order_id}
    exec_res = make_execution_result(
        method="GET",
        path_template="/orders/{order_id}",
        status_code=204,  # No Content is not documented
        resp_body=None,
        is_json=False,
    )

    findings = oracle.check(exec_res)
    assert len(findings) == 1
    f = findings[0]
    assert f.bug_type == "UNDOCUMENTED_STATUS_CODE"
    assert "204" in f.explanation


def test_schema_conformance_passes_valid_response(sample_spec):
    """Verify conforming response is NOT flagged (no false positives)."""
    oracle = SchemaConformanceOracle(spec=sample_spec)

    valid_body = {
        "id": "ord-1",
        "user_id": "user-alice",
        "total_price": 49.99,
        "status": "completed",
    }
    exec_res = make_execution_result(
        method="GET",
        path_template="/orders/{order_id}",
        status_code=200,
        resp_body=valid_body,
    )

    findings = oracle.check(exec_res)
    assert len(findings) == 0


def test_schema_conformance_handles_undocumented_endpoints_gracefully(sample_spec):
    """Verify unknown endpoint does not crash and does not invent rules."""
    oracle = SchemaConformanceOracle(spec=sample_spec)

    exec_res = make_execution_result(
        method="GET",
        path_template="/unknown/custom/endpoint",
        status_code=200,
        resp_body={"foo": "bar"},
    )

    findings = oracle.check(exec_res)
    assert findings == []


def test_schema_conformance_detects_non_json_for_json_schema(sample_spec):
    """Verify returning HTML or plaintext when JSON schema is documented is flagged."""
    oracle = SchemaConformanceOracle(spec=sample_spec)

    exec_res = make_execution_result(
        method="GET",
        path_template="/orders/{order_id}",
        status_code=200,
        resp_body="<html>Error Page</html>",
        is_json=False,
        resp_headers={"content-type": "text/html"},
    )

    findings = oracle.check(exec_res)
    assert len(findings) == 1
    assert findings[0].bug_type == "SCHEMA_MISMATCH"
    assert "non-JSON" in findings[0].explanation


# ------------------------------------------------------------------------------
# Check 3: Broken Object Level Authorization (BOLA) Tests
# ------------------------------------------------------------------------------

def test_bola_oracle_flags_unauthorized_cross_user_access():
    """Verify Bob accessing Alice's private order generates a critical confirmed BOLA finding."""
    oracle = BOLAOracle()

    # Bob (user-bob) retrieves order owned by Alice (user-alice)
    alice_order_body = {
        "id": "ord-1",
        "user_id": "user-alice",
        "item_name": "Drone",
        "total_price": 299.99,
    }
    exec_res = make_execution_result(
        method="GET",
        path_template="/orders/{order_id}",
        headers={"authorization": "Bearer bob_secret_token"},
        status_code=200,
        resp_body=alice_order_body,
    )

    finding = oracle.check_access(
        execution_result=exec_res,
        resource_owner_id="user-alice",
        accessor_user_id="user-bob",
        resource_id="ord-1",
        endpoint_template="/orders/{order_id}",
    )

    assert finding is not None
    assert finding.bug_type == "BOLA_VIOLATION"
    assert finding.severity == "CRITICAL"
    assert finding.is_confirmed is True
    assert "user-bob" in finding.explanation
    assert "user-alice" in finding.explanation
    assert finding.evidence["resource_id"] == "ord-1"
    assert finding.evidence["resource_owner_id"] == "user-alice"
    assert finding.evidence["accessor_user_id"] == "user-bob"


def test_bola_oracle_allows_legitimate_owner_access():
    """Verify Alice accessing her own order does NOT trigger a BOLA finding."""
    oracle = BOLAOracle()

    alice_order_body = {
        "id": "ord-1",
        "user_id": "user-alice",
        "item_name": "Drone",
        "total_price": 299.99,
    }
    exec_res = make_execution_result(
        method="GET",
        path_template="/orders/{order_id}",
        headers={"authorization": "Bearer alice_secret_token"},
        status_code=200,
        resp_body=alice_order_body,
    )

    finding = oracle.check_access(
        execution_result=exec_res,
        resource_owner_id="user-alice",
        accessor_user_id="user-alice",  # Legitimate owner
        resource_id="ord-1",
    )

    assert finding is None


def test_bola_oracle_ignores_rejected_access():
    """Verify that when the API correctly returns HTTP 403 or 404, no BOLA is flagged."""
    oracle = BOLAOracle()

    exec_res = make_execution_result(
        method="GET",
        path_template="/orders/{order_id}",
        status_code=403,
        resp_body={"detail": "Forbidden: You do not own this order"},
    )

    finding = oracle.check_access(
        execution_result=exec_res,
        resource_owner_id="user-alice",
        accessor_user_id="user-bob",
        resource_id="ord-1",
    )

    assert finding is None


# ------------------------------------------------------------------------------
# Sensitive Credential Redaction in Findings
# ------------------------------------------------------------------------------

def test_sensitive_credentials_redacted_in_findings():
    """Verify Authorization tokens and passwords are fully hidden in finding reports."""
    oracle = ServerErrorOracle()

    exec_res = make_execution_result(
        method="POST",
        url="http://127.0.0.1:8000/auth/login",
        path_template="/auth/login",
        headers={"authorization": "Bearer super_secret_token", "x-api-key": "secret123"},
        req_body={"username": "alice", "password": "plaintext_password_123"},
        status_code=500,
        resp_body={"detail": "Database crash", "access_token": "leak_token_456"},
    )

    finding = oracle.check(exec_res)
    assert finding is not None

    # Check request headers
    assert finding.request_details["headers"]["authorization"] == "Bearer [REDACTED]"
    assert finding.request_details["headers"]["x-api-key"] == "[REDACTED]"

    # Check request body
    assert finding.request_details["body"]["password"] == "[REDACTED]"

    # Check response body
    assert finding.actual_response["body"]["access_token"] == "[REDACTED]"

    # Verify serialized finding contains no secret tokens
    finding_json = finding.model_dump_json()
    assert "super_secret_token" not in finding_json
    assert "secret123" not in finding_json
    assert "plaintext_password_123" not in finding_json
    assert "leak_token_456" not in finding_json


# ------------------------------------------------------------------------------
# End-to-End Integration Test with Running Sample API
# ------------------------------------------------------------------------------

def test_e2e_sample_api_detects_deliberate_bola_vulnerability():
    """Execute live BOLA detection against the running Sample Shopping API.

    Verifies the complete Step 5 scenario:
    1. Reset state.
    2. Alice logs in and creates an order.
    3. Bob logs in and accesses Alice's order.
    4. BOLAOracle flags the deliberate vulnerability on GET /orders/{order_id}.
    5. Control test confirms Alice can access her own order without flagging.
    """
    executor = RequestExecutor(base_url="http://127.0.0.1:8000")

    # Reset test database state
    reset_res = executor.post("/admin/reset")
    assert reset_res.status_code == 200

    detector = BugDetector()
    finding, metadata = detector.run_bola_test(executor=executor)

    # 1. BOLA finding must be detected and confirmed
    assert finding is not None
    assert finding.bug_type == "BOLA_VIOLATION"
    assert finding.severity == "CRITICAL"
    assert finding.is_confirmed is True
    assert finding.endpoint == "/orders/{order_id}"
    assert "user-bob" in finding.explanation
    assert "user-alice" in finding.explanation

    # 2. Evidence must contain the resource ID and owner
    assert metadata["order_id"] is not None
    assert metadata["bob_status_code"] == 200
    assert metadata["control_passed"] is True
    assert metadata["alice_status_code"] == 200

    # 3. Formatted report card should be printable without encoding errors
    report_text = finding.format_report()
    assert "CONFIRMED BUG" in report_text
    assert "OWASP API Security Top 10" in report_text
