"""Bug Detection Oracles for Autonomous AI Testing Agent for REST APIs.

Oracles represent deterministic rules and validators that evaluate API execution
results to identify functional defects, specification mismatches, and security
vulnerabilities (specifically Broken Object Level Authorization / BOLA).
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union
import httpx
from pydantic import BaseModel, Field
import jsonschema

from agent.executor import (
    ExecutionResult,
    RequestExecutor,
    redact_headers,
    redact_payload,
)
from agent.spec_reader import (
    APISpecification,
    OperationDefinition,
    ResponseDefinition,
)

logger = logging.getLogger("agent.oracles")


# ------------------------------------------------------------------------------
# Structured Bug Finding Model
# ------------------------------------------------------------------------------

class BugFinding(BaseModel):
    """Structured record of an identified API defect or security vulnerability."""

    __test__ = False  # Prevent pytest from collecting this class as a test suite

    finding_id: str = Field(default_factory=lambda: f"finding-{uuid.uuid4().hex[:8]}")
    bug_type: str = Field(
        ...,
        description="Classification: 'SERVER_ERROR_5XX', 'SCHEMA_MISMATCH', 'UNDOCUMENTED_STATUS_CODE', 'BOLA_VIOLATION'",
    )
    severity: str = Field(
        ...,
        description="Severity rating: 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW', or 'INFO'",
    )
    endpoint: str = Field(..., description="Target endpoint path template or URL")
    method: str = Field(..., description="HTTP Method (GET, POST, etc.)")
    request_details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Sanitized request details with credentials and tokens redacted",
    )
    expected_behavior: str = Field(
        ...,
        description="Expected behavior according to OpenAPI spec or authorization policy",
    )
    actual_response: Dict[str, Any] = Field(
        default_factory=dict,
        description="Sanitized actual response details with credentials redacted",
    )
    explanation: str = Field(
        ...,
        description="Plain-language explanation of why this observation appears to be a bug",
    )
    evidence: Dict[str, Any] = Field(
        default_factory=dict,
        description="Concrete factual evidence supporting the finding",
    )
    is_confirmed: bool = Field(
        default=False,
        description="True if proven bug/vulnerability; False if suspicious/possible bug requiring investigation",
    )

    def summary(self) -> str:
        """One-line human-readable summary of the finding."""
        status_tag = "CONFIRMED" if self.is_confirmed else "POSSIBLE"
        return f"[{status_tag} {self.severity}] {self.bug_type} on {self.method} {self.endpoint}: {self.explanation}"

    def format_report(self) -> str:
        """Multi-line ASCII formatted report card for terminal display."""
        status_tag = "CONFIRMED BUG" if self.is_confirmed else "SUSPICIOUS / POSSIBLE BUG"
        lines = [
            "=" * 76,
            f"BUG FINDING: {self.finding_id} [{status_tag}]",
            "=" * 76,
            f"Type:       {self.bug_type}",
            f"Severity:   {self.severity}",
            f"Endpoint:   {self.method} {self.endpoint}",
            f"Confirmed:  {'Yes' if self.is_confirmed else 'No (Requires Verification / Investigation)'}",
            "-" * 76,
            "EXPLANATION:",
            f"  {self.explanation}",
            "-" * 76,
            "EXPECTED BEHAVIOR:",
            f"  {self.expected_behavior}",
            "-" * 76,
            "ACTUAL RESPONSE:",
            f"  Status Code: {self.actual_response.get('status_code')}",
            f"  Body:        {json.dumps(self.actual_response.get('body'), indent=2)}",
            "-" * 76,
            "REQUEST DETAILS (REDACTED):",
            f"  URL:         {self.request_details.get('url')}",
            f"  Headers:     {json.dumps(self.request_details.get('headers'), indent=2)}",
            f"  Payload:     {json.dumps(self.request_details.get('body'), indent=2)}",
            "-" * 76,
            "EVIDENCE:",
            f"  {json.dumps(self.evidence, indent=2)}",
            "=" * 76,
        ]
        return "\n".join(lines)


# ------------------------------------------------------------------------------
# Check 1: Unexpected Server Errors Oracle
# ------------------------------------------------------------------------------

class ServerErrorOracle:
    """Oracle that identifies unexpected HTTP 5xx server-side errors.

    If a request returns a server error such as HTTP 500, record a possible problem
    for further investigation. Does not automatically mark every 5xx response as a confirmed
    bug, but captures sanitized request and response details for root cause analysis.
    """

    __test__ = False

    def check(self, execution_result: ExecutionResult) -> Optional[BugFinding]:
        """Inspect execution result for 5xx server status codes."""
        if execution_result.response is None:
            return None

        status = execution_result.response.status_code
        if 500 <= status <= 599:
            req_details = {
                "url": execution_result.request.url,
                "path_template": execution_result.request.path_template,
                "headers": redact_headers(execution_result.request.headers),
                "body": redact_payload(execution_result.request.body),
                "path_params": execution_result.request.path_params,
                "query_params": execution_result.request.query_params,
            }
            resp_details = {
                "status_code": status,
                "headers": redact_headers(execution_result.response.headers),
                "body": redact_payload(execution_result.response.body),
                "is_json": execution_result.response.is_json,
            }

            return BugFinding(
                bug_type="SERVER_ERROR_5XX",
                severity="HIGH",
                endpoint=execution_result.request.path_template or execution_result.request.url,
                method=execution_result.request.method,
                request_details=req_details,
                expected_behavior=(
                    "API should process the request or return a graceful client error (HTTP 4xx). "
                    "Server must not crash or return unhandled 5xx internal server errors."
                ),
                actual_response=resp_details,
                explanation=(
                    f"Unexpected HTTP {status} server error on {execution_result.request.method} "
                    f"{execution_result.request.path_template or execution_result.request.url}. "
                    "This indicates an unhandled server-side exception or crash and should be investigated."
                ),
                evidence={
                    "status_code": status,
                    "server_error_range": "5xx Internal Server Error",
                    "error_summary": (
                        redact_payload(execution_result.response.body)
                        if execution_result.response.is_json
                        else "[NON_JSON_RESPONSE]"
                    ),
                },
                is_confirmed=False,  # Flagged as possible problem requiring investigation
            )
        return None


# ------------------------------------------------------------------------------
# Check 2: Response Documentation Conformance Oracle
# ------------------------------------------------------------------------------

class SchemaConformanceOracle:
    """Oracle that validates actual API responses against the OpenAPI specification.

    Compares actual responses against documented status codes and response schemas.
    - Flags undocumented status codes when not listed in the spec.
    - Validates response payloads against documented JSON schemas (types, missing fields).
    - If expected behavior is not documented, does not invent a rule.
    - Ignores 5xx server errors (handled by ServerErrorOracle).
    """

    __test__ = False

    def __init__(self, spec: Optional[APISpecification] = None):
        self.spec = spec

    def check(
        self,
        execution_result: ExecutionResult,
        operation: Optional[OperationDefinition] = None,
    ) -> List[BugFinding]:
        """Validate response status and payload against documented OpenAPI operation."""
        if execution_result.response is None or execution_result.has_error:
            return []

        status_code = execution_result.response.status_code
        # 5xx responses are handled by ServerErrorOracle
        if status_code >= 500:
            return []

        # Resolve operation from spec if not supplied
        op = operation
        if op is None and self.spec is not None:
            op = self.spec.get_operation(
                execution_result.request.method,
                execution_result.request.path_template,
            )
            if op is None:
                # Fallback to URL path comparison
                req_path = httpx.URL(execution_result.request.url).path
                for candidate in self.spec.operations:
                    if candidate.method == execution_result.request.method.upper() and candidate.path == req_path:
                        op = candidate
                        break

        # If operation is not documented in the specification, do not invent a rule
        if op is None:
            return []

        findings: List[BugFinding] = []
        status_str = str(status_code)
        documented_responses = op.responses

        # 1. Check status code conformance
        has_status_match = (
            status_str in documented_responses
            or "default" in documented_responses
            or f"{status_str[0]}XX" in documented_responses
        )

        if not has_status_match:
            req_details = {
                "url": execution_result.request.url,
                "path_template": execution_result.request.path_template,
                "headers": redact_headers(execution_result.request.headers),
                "body": redact_payload(execution_result.request.body),
            }
            resp_details = {
                "status_code": status_code,
                "headers": redact_headers(execution_result.response.headers),
                "body": redact_payload(execution_result.response.body),
            }
            documented_codes = list(documented_responses.keys())
            findings.append(
                BugFinding(
                    bug_type="UNDOCUMENTED_STATUS_CODE",
                    severity="LOW",
                    endpoint=op.path,
                    method=op.method,
                    request_details=req_details,
                    expected_behavior=f"HTTP status code documented in specification: {documented_codes}",
                    actual_response=resp_details,
                    explanation=(
                        f"Endpoint {op.method} {op.path} returned HTTP {status_code}, which is not "
                        f"documented in the OpenAPI specification (documented: {documented_codes})."
                    ),
                    evidence={
                        "returned_status_code": status_code,
                        "documented_status_codes": documented_codes,
                    },
                    is_confirmed=True,
                )
            )
            return findings

        # 2. Check response body schema conformance
        resp_def: Optional[ResponseDefinition] = documented_responses.get(status_str) or documented_responses.get("default")
        if not resp_def:
            return findings

        # Find documented JSON schema
        json_schema = resp_def.schemas.get("application/json")
        if not json_schema:
            for ct, s in resp_def.schemas.items():
                if "json" in ct.lower():
                    json_schema = s
                    break

        # If no schema is documented for this response, do not invent a rule
        if not json_schema:
            return findings

        # If schema is defined for JSON, response body must be valid JSON
        if not execution_result.response.is_json:
            req_details = {
                "url": execution_result.request.url,
                "path_template": execution_result.request.path_template,
                "headers": redact_headers(execution_result.request.headers),
                "body": redact_payload(execution_result.request.body),
            }
            resp_details = {
                "status_code": status_code,
                "headers": redact_headers(execution_result.response.headers),
                "body": execution_result.response.text[:200],
            }
            findings.append(
                BugFinding(
                    bug_type="SCHEMA_MISMATCH",
                    severity="MEDIUM",
                    endpoint=op.path,
                    method=op.method,
                    request_details=req_details,
                    expected_behavior=f"Valid JSON response body matching schema for HTTP {status_code}.",
                    actual_response=resp_details,
                    explanation=(
                        f"Endpoint {op.method} {op.path} returned non-JSON content for HTTP {status_code}, "
                        "violating documented 'application/json' schema requirement."
                    ),
                    evidence={
                        "response_content_type": execution_result.response.headers.get("content-type"),
                    },
                    is_confirmed=True,
                )
            )
            return findings

        # Validate JSON payload against schema using jsonschema
        body = execution_result.response.body
        validation_errors = self._validate_payload_schema(body, json_schema)
        if validation_errors:
            req_details = {
                "url": execution_result.request.url,
                "path_template": execution_result.request.path_template,
                "headers": redact_headers(execution_result.request.headers),
                "body": redact_payload(execution_result.request.body),
            }
            resp_details = {
                "status_code": status_code,
                "headers": redact_headers(execution_result.response.headers),
                "body": redact_payload(body),
            }
            err_summary = "; ".join(validation_errors[:3])
            if len(validation_errors) > 3:
                err_summary += f" (and {len(validation_errors) - 3} more errors)"

            findings.append(
                BugFinding(
                    bug_type="SCHEMA_MISMATCH",
                    severity="MEDIUM",
                    endpoint=op.path,
                    method=op.method,
                    request_details=req_details,
                    expected_behavior=f"Response body conforming to OpenAPI schema for HTTP {status_code}.",
                    actual_response=resp_details,
                    explanation=f"Response body violates documented schema for HTTP {status_code}: {err_summary}",
                    evidence={
                        "schema_violations": validation_errors,
                        "schema_title": json_schema.get("title", "ResponseSchema"),
                    },
                    is_confirmed=True,
                )
            )

        return findings

    @classmethod
    def _validate_payload_schema(cls, payload: Any, schema: Dict[str, Any]) -> List[str]:
        """Validate payload against schema returning human-readable error messages."""
        errors: List[str] = []
        try:
            validator_cls = jsonschema.validators.validator_for(schema)
            validator = validator_cls(schema)
            for err in validator.iter_errors(payload):
                field_path = ".".join(str(p) for p in err.path) if err.path else "root"
                errors.append(f"Field '{field_path}': {err.message}")
        except Exception as exc:
            logger.warning("Error during JSON schema validation: %s", exc)
        return errors


# ------------------------------------------------------------------------------
# Check 3: Broken Object Level Authorization (BOLA) Oracle
# ------------------------------------------------------------------------------

class BOLAOracle:
    """Oracle that tests for Broken Object Level Authorization (OWASP API1:2023).

    Verifies the access control rule:
    Only the owner of a private resource may view or modify it.
    If an authenticated user accesses another user's private resource,
    flags a confirmed BOLA security vulnerability with full evidence.
    """

    __test__ = False

    def check_access(
        self,
        execution_result: ExecutionResult,
        resource_owner_id: str,
        accessor_user_id: str,
        resource_id: str,
        endpoint_template: str = "/orders/{order_id}",
    ) -> Optional[BugFinding]:
        """Evaluate an individual resource retrieval result for BOLA violation.

        Args:
            execution_result: Captured HTTP response.
            resource_owner_id: ID of the user who owns the resource (e.g. 'user-alice').
            accessor_user_id: ID of the user making the request (e.g. 'user-bob').
            resource_id: Identifier of the resource being accessed (e.g. 'ord-1').
            endpoint_template: Path template of the endpoint.

        Returns:
            BugFinding if unauthorized access is confirmed, otherwise None.
        """
        if execution_result.response is None or execution_result.has_error:
            return None

        # If accessor IS the owner, access is legitimate and allowed
        if accessor_user_id == resource_owner_id:
            return None

        status = execution_result.response.status_code
        # Successful response (2xx) when accessor is NOT owner indicates BOLA
        if 200 <= status < 300 and execution_result.response.is_json:
            body = execution_result.response.body
            returned_owner = body.get("user_id") if isinstance(body, dict) else None

            # Confirm that the returned object actually belongs to resource_owner_id
            if returned_owner == resource_owner_id:
                req_details = {
                    "url": execution_result.request.url,
                    "path_template": execution_result.request.path_template or endpoint_template,
                    "headers": redact_headers(execution_result.request.headers),
                    "body": redact_payload(execution_result.request.body),
                    "path_params": execution_result.request.path_params,
                }
                resp_details = {
                    "status_code": status,
                    "headers": redact_headers(execution_result.response.headers),
                    "body": redact_payload(body),
                }

                return BugFinding(
                    bug_type="BOLA_VIOLATION",
                    severity="CRITICAL",
                    endpoint=endpoint_template,
                    method=execution_result.request.method,
                    request_details=req_details,
                    expected_behavior=(
                        f"Access denied (HTTP 403 Forbidden or HTTP 404 Not Found). "
                        f"User '{accessor_user_id}' does not own resource '{resource_id}' "
                        f"(owned by '{resource_owner_id}')."
                    ),
                    actual_response=resp_details,
                    explanation=(
                        f"Broken Object Level Authorization (BOLA / OWASP API1:2023) detected: "
                        f"User '{accessor_user_id}' successfully accessed private resource '{resource_id}' "
                        f"belonging to user '{resource_owner_id}'. The API failed to enforce object ownership."
                    ),
                    evidence={
                        "vulnerability_standard": "OWASP API Security Top 10 (2023) - API1: BOLA",
                        "resource_id": resource_id,
                        "resource_owner_id": resource_owner_id,
                        "accessor_user_id": accessor_user_id,
                        "returned_owner_id": returned_owner,
                        "is_unauthorized_access": True,
                    },
                    is_confirmed=True,  # Proven security vulnerability
                )

        return None

    def test_sample_api_orders_bola(
        self,
        executor: RequestExecutor,
        alice_user: str = "alice",
        alice_pass: str = "alice123",
        bob_user: str = "bob",
        bob_pass: str = "bob123",
    ) -> Tuple[Optional[BugFinding], Dict[str, Any]]:
        """Run the end-to-end BOLA cross-user test sequence against the sample API.

        Workflow:
        1. Log in as Alice and retrieve her access token and user_id.
        2. Create a private order under Alice's account (POST /orders).
        3. Log in as Bob and retrieve his access token and user_id.
        4. Attempt to access Alice's order using Bob's Bearer token (GET /orders/{order_id}).
        5. Check whether Bob receives Alice's private order (BOLA violation).
        6. Verify control case: Alice accessing her own order is permitted.

        Returns:
            Tuple of (Optional[BugFinding], metadata_dict)
        """
        # Step 1: Login as Alice
        alice_login = executor.post("/auth/login", json_body={"username": alice_user, "password": alice_pass})
        if not alice_login.is_success or not alice_login.response.is_json:
            raise RuntimeError(f"Failed to authenticate as '{alice_user}': {alice_login.summary()}")
        alice_token = alice_login.response.body.get("access_token")
        alice_id = alice_login.response.body.get("user_id")

        # Step 2: Alice creates an order
        order_payload = {
            "item_name": "Autonomous Testing Drone",
            "quantity": 1,
            "total_price": 299.99,
        }
        order_create = executor.post("/orders", auth_token=alice_token, json_body=order_payload)
        if not order_create.is_success or not order_create.response.is_json:
            raise RuntimeError(f"Failed to create order as '{alice_user}': {order_create.summary()}")
        order_id = order_create.response.body.get("id")

        # Step 3: Login as Bob
        bob_login = executor.post("/auth/login", json_body={"username": bob_user, "password": bob_pass})
        if not bob_login.is_success or not bob_login.response.is_json:
            raise RuntimeError(f"Failed to authenticate as '{bob_user}': {bob_login.summary()}")
        bob_token = bob_login.response.body.get("access_token")
        bob_id = bob_login.response.body.get("user_id")

        # Step 4: Bob attempts to access Alice's order
        bob_access = executor.get(
            path="/orders/{order_id}",
            path_params={"order_id": order_id},
            auth_token=bob_token,
        )

        # Step 5: Check BOLA rule on Bob's attempt
        finding = self.check_access(
            execution_result=bob_access,
            resource_owner_id=alice_id,
            accessor_user_id=bob_id,
            resource_id=order_id,
            endpoint_template="/orders/{order_id}",
        )

        # Step 6: Control check - Alice accessing her own order
        alice_access = executor.get(
            path="/orders/{order_id}",
            path_params={"order_id": order_id},
            auth_token=alice_token,
        )
        control_finding = self.check_access(
            execution_result=alice_access,
            resource_owner_id=alice_id,
            accessor_user_id=alice_id,
            resource_id=order_id,
            endpoint_template="/orders/{order_id}",
        )

        metadata = {
            "order_id": order_id,
            "alice_user_id": alice_id,
            "bob_user_id": bob_id,
            "bob_status_code": bob_access.status_code,
            "alice_status_code": alice_access.status_code,
            "control_passed": (control_finding is None and alice_access.is_success),
        }

        return finding, metadata


# ------------------------------------------------------------------------------
# Unified Bug Detector Coordinator
# ------------------------------------------------------------------------------

class BugDetector:
    """Unified bug detection coordinator combining all active oracles."""

    __test__ = False

    def __init__(self, spec: Optional[APISpecification] = None):
        self.spec = spec
        self.server_error_oracle = ServerErrorOracle()
        self.schema_oracle = SchemaConformanceOracle(spec=spec)
        self.bola_oracle = BOLAOracle()

    def analyze_execution(
        self,
        execution_result: ExecutionResult,
        operation: Optional[OperationDefinition] = None,
    ) -> List[BugFinding]:
        """Run all single-execution oracles against an ExecutionResult."""
        findings: List[BugFinding] = []

        # 1. Check 5xx server errors
        server_finding = self.server_error_oracle.check(execution_result)
        if server_finding:
            findings.append(server_finding)

        # 2. Check OpenAPI schema conformance
        schema_findings = self.schema_oracle.check(execution_result, operation=operation)
        findings.extend(schema_findings)

        return findings

    def run_bola_test(
        self,
        executor: RequestExecutor,
        alice_user: str = "alice",
        alice_pass: str = "alice123",
        bob_user: str = "bob",
        bob_pass: str = "bob123",
    ) -> Tuple[Optional[BugFinding], Dict[str, Any]]:
        """Run the end-to-end BOLA cross-user security test sequence."""
        return self.bola_oracle.test_sample_api_orders_bola(
            executor=executor,
            alice_user=alice_user,
            alice_pass=alice_pass,
            bob_user=bob_user,
            bob_pass=bob_pass,
        )


if __name__ == "__main__":
    import sys

    target_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    print(f"[*] Running Bug Detection Oracles against: {target_url}")

    cli_executor = RequestExecutor(base_url=target_url)

    # Reset state if available
    reset_resp = cli_executor.post("/admin/reset")
    if reset_resp.is_success:
        print("[*] Successfully reset test database state.")

    # Run BOLA security oracle
    print("[*] Executing BOLA (Broken Object Level Authorization) security oracle...")
    detector = BugDetector()
    bola_finding, meta = detector.run_bola_test(executor=cli_executor)

    if bola_finding:
        print("\n" + bola_finding.format_report() + "\n")
    else:
        print("[*] No BOLA vulnerability detected.")

