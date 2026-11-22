"""Automatic Test Generator and Sequence Runner for Autonomous AI Testing Agent.

Generates normal (positive) and invalid-input (negative) test cases based on OpenAPI
specifications, executes them using RequestExecutor, validates responses against documented
expectations, and executes dependent request sequences via APIDependencyGraph.
"""

from __future__ import annotations

import json
import logging
import uuid
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field

from agent.spec_reader import (
    APISpecification,
    OperationDefinition,
    ParameterDefinition,
    RequestBodyDefinition,
)
from agent.executor import RequestExecutor, ExecutionResult
from agent.dependency_graph import APIDependencyGraph, SequencePlan, SequenceStep

logger = logging.getLogger("agent.test_generator")


# ------------------------------------------------------------------------------
# Structured Test Models
# ------------------------------------------------------------------------------

class TestCase(BaseModel):
    """Specification of an executable API test case."""

    __test__ = False  # Prevent pytest from collecting this class as a test suite

    test_id: str = Field(default_factory=lambda: f"test-{uuid.uuid4().hex[:8]}")
    name: str = Field(..., description="Human-readable test case name")
    test_type: str = Field(..., description="Test classification: 'normal', 'invalid_input', 'auth', or 'sequence_step'")
    operation_key: str = Field(..., description="Target operation (e.g. 'POST /orders')")
    method: str = Field(..., description="HTTP Method")
    path_template: str = Field(..., description="Path template (e.g. '/orders/{order_id}')")
    path_params: Dict[str, Any] = Field(default_factory=dict, description="Parameters substituted into the URL path")
    query_params: Dict[str, Any] = Field(default_factory=dict, description="Query string parameters")
    headers: Dict[str, str] = Field(default_factory=dict, description="Custom request headers")
    json_body: Optional[Any] = Field(default=None, description="Request body payload")
    auth_token: Optional[str] = Field(default=None, description="Explicit authentication Bearer token")
    as_user: Optional[str] = Field(default=None, description="User identity to execute as ('alice', 'bob')")
    expected_status_codes: List[int] = Field(default_factory=list, description="Expected HTTP response status codes")
    description: str = Field(default="", description="Explanation of what this test verifies")
    mutation_type: Optional[str] = Field(default=None, description="Type of mutation applied for invalid-input tests")


class TestResult(BaseModel):
    """Outcome of an executed test case."""

    __test__ = False  # Prevent pytest from collecting this class as a test suite

    test_case: TestCase
    execution_result: ExecutionResult
    status: str = Field(..., description="'PASSED', 'FAILED', or 'ERROR'")
    reason: str = Field(..., description="Detailed explanation of the pass/fail determination")

    @property
    def is_passed(self) -> bool:
        return self.status == "PASSED"

    def summary(self) -> str:
        return f"[{self.status}] {self.test_case.name}: {self.reason} ({self.execution_result.duration_ms:.1f}ms)"


class SequenceResult(BaseModel):
    """Outcome of a multi-step dependent request sequence."""

    plan_name: str
    target_operation: str
    step_results: List[TestResult] = Field(default_factory=list)
    context_values: Dict[str, Any] = Field(default_factory=dict)
    all_passed: bool = Field(default=True)

    def summary(self) -> str:
        status_str = "SUCCESS" if self.all_passed else "FAILURE"
        return f"[SEQUENCE {status_str}] {self.plan_name}: {len(self.step_results)} steps executed."


# ------------------------------------------------------------------------------
# Schema Synthesizer & Mutator
# ------------------------------------------------------------------------------

class SchemaSynthesizer:
    """Generates valid and invalid payloads derived from JSON schema definitions."""

    @classmethod
    def generate_valid_value(cls, schema: Dict[str, Any], field_name: str = "") -> Any:
        """Synthesize a valid value complying with the given JSON schema."""
        if not schema:
            return "sample_value"

        # Check examples
        if "examples" in schema and isinstance(schema["examples"], list) and len(schema["examples"]) > 0:
            return deepcopy(schema["examples"][0])
        if "example" in schema:
            return deepcopy(schema["example"])
        if "default" in schema:
            return deepcopy(schema["default"])

        # Check enum
        if "enum" in schema and isinstance(schema["enum"], list) and len(schema["enum"]) > 0:
            return schema["enum"][0]

        schema_type = schema.get("type", "string")

        if schema_type == "string":
            name_lower = field_name.lower()
            if "username" in name_lower:
                return "alice"
            if "password" in name_lower:
                return "alice123"
            if "email" in name_lower:
                return "alice@example.com"
            if "item" in name_lower or "name" in name_lower:
                return "Wireless Headphones"
            return "sample_text"

        if schema_type == "integer":
            min_val = schema.get("minimum", schema.get("gt", 0))
            return max(int(min_val) + 1, 1)

        if schema_type == "number":
            min_val = schema.get("minimum", schema.get("ge", 0.0))
            return max(float(min_val) + 1.0, 10.0)

        if schema_type == "boolean":
            return True

        if schema_type == "array":
            items_schema = schema.get("items", {})
            return [cls.generate_valid_value(items_schema, field_name)]

        if schema_type == "object":
            properties = schema.get("properties", {})
            obj: Dict[str, Any] = {}
            for prop_name, prop_schema in properties.items():
                obj[prop_name] = cls.generate_valid_value(prop_schema, prop_name)
            return obj

        return "test_val"

    @classmethod
    def generate_valid_body(cls, req_body: Optional[RequestBodyDefinition]) -> Optional[Any]:
        """Generate a valid request body using the operation's application/json schema."""
        if not req_body or not req_body.schemas:
            return None

        schema = req_body.schemas.get("application/json")
        if not schema:
            # Fallback to first available schema
            schema = next(iter(req_body.schemas.values()), {})

        return cls.generate_valid_value(schema)


# ------------------------------------------------------------------------------
# Automatic Test Generator
# ------------------------------------------------------------------------------

class TestGenerator:
    """Generates normal, invalid-input, and sequenced API tests from an APISpecification."""

    __test__ = False  # Prevent pytest from collecting this class as a test suite

    def __init__(self, spec: APISpecification):
        self.spec: APISpecification = spec
        self.dep_graph: APIDependencyGraph = APIDependencyGraph(spec)

    # --------------------------------------------------------------------------
    # Normal Test Generation
    # --------------------------------------------------------------------------

    def generate_normal_tests(self) -> List[TestCase]:
        """Generate positive test cases with valid inputs for all endpoints."""
        tests: List[TestCase] = []

        for op in self.spec.operations:
            op_key = APIDependencyGraph.get_op_key(op)

            # Generate valid body if required or defined
            body = SchemaSynthesizer.generate_valid_body(op.request_body)

            # Generate valid path parameters
            path_params: Dict[str, Any] = {}
            for param in op.parameters:
                if param.location == "path":
                    # Use sample valid ID
                    path_params[param.name] = "ord-1" if "order" in param.name else "test-id-1"

            # Expected status codes: extract documented 2xx codes (e.g. 200, 201)
            expected_codes = [
                int(code) for code in op.responses.keys()
                if code.isdigit() and code.startswith("2")
            ]
            if not expected_codes:
                expected_codes = [200]

            # If endpoint requires auth, set as_user to 'alice' by default
            user = "alice" if op.security else None

            test_case = TestCase(
                name=f"Normal: {op.method} {op.path}",
                test_type="normal",
                operation_key=op_key,
                method=op.method,
                path_template=op.path,
                path_params=path_params,
                json_body=body,
                as_user=user,
                expected_status_codes=expected_codes,
                description=f"Send valid inputs to {op_key} and expect documented 2xx response.",
            )
            tests.append(test_case)

        return tests

    # --------------------------------------------------------------------------
    # Invalid-Input Test Generation
    # --------------------------------------------------------------------------

    def generate_invalid_input_tests(self) -> List[TestCase]:
        """Generate negative test cases testing missing fields, wrong types, and violations."""
        tests: List[TestCase] = []

        for op in self.spec.operations:
            op_key = APIDependencyGraph.get_op_key(op)
            valid_body = SchemaSynthesizer.generate_valid_body(op.request_body)

            # 1. Missing Required Field Tests
            if isinstance(valid_body, dict) and op.request_body:
                schema = op.request_body.schemas.get("application/json", {})
                required_fields = schema.get("required", list(valid_body.keys()))

                for field in required_fields:
                    mutated_body = deepcopy(valid_body)
                    mutated_body.pop(field, None)

                    test = TestCase(
                        name=f"Invalid Input: {op.method} {op.path} (missing '{field}')",
                        test_type="invalid_input",
                        mutation_type="missing_required_field",
                        operation_key=op_key,
                        method=op.method,
                        path_template=op.path,
                        json_body=mutated_body,
                        as_user="alice" if op.security else None,
                        expected_status_codes=[400, 422],
                        description=f"Omit required field '{field}' from request body and expect 400 or 422.",
                    )
                    tests.append(test)

                # 2. Type Mismatch Tests
                properties = schema.get("properties", {})
                for prop_name, prop_schema in properties.items():
                    prop_type = prop_schema.get("type")
                    if prop_type in ("integer", "number"):
                        mutated_body = deepcopy(valid_body)
                        mutated_body[prop_name] = "not_a_number_string"

                        test = TestCase(
                            name=f"Invalid Input: {op.method} {op.path} (type mismatch on '{prop_name}')",
                            test_type="invalid_input",
                            mutation_type="type_mismatch",
                            operation_key=op_key,
                            method=op.method,
                            path_template=op.path,
                            json_body=mutated_body,
                            as_user="alice" if op.security else None,
                            expected_status_codes=[400, 422],
                            description=f"Send string instead of {prop_type} for '{prop_name}' and expect 400 or 422.",
                        )
                        tests.append(test)

                    # 3. Constraint / Boundary Violations
                    if prop_type in ("integer", "number") and ("gt" in prop_schema or "ge" in prop_schema or "minimum" in prop_schema):
                        mutated_body = deepcopy(valid_body)
                        mutated_body[prop_name] = -999  # Violates ge=0 or gt=0

                        test = TestCase(
                            name=f"Invalid Input: {op.method} {op.path} (negative value on '{prop_name}')",
                            test_type="invalid_input",
                            mutation_type="boundary_violation",
                            operation_key=op_key,
                            method=op.method,
                            path_template=op.path,
                            json_body=mutated_body,
                            as_user="alice" if op.security else None,
                            expected_status_codes=[400, 422],
                            description=f"Send negative number violating constraints on '{prop_name}'.",
                        )
                        tests.append(test)

            # 4. Missing Path Parameter Tests
            path_params = [p for p in op.parameters if p.location == "path"]
            for p in path_params:
                # Test with non-existent ID
                test = TestCase(
                    name=f"Invalid Input: {op.method} {op.path} (non-existent '{p.name}')",
                    test_type="invalid_input",
                    mutation_type="nonexistent_resource",
                    operation_key=op_key,
                    method=op.method,
                    path_template=op.path,
                    path_params={p.name: "nonexistent-resource-id-99999"},
                    as_user="alice" if op.security else None,
                    expected_status_codes=[404],
                    description=f"Query non-existent {p.name} and expect HTTP 404.",
                )
                tests.append(test)

            # 5. Missing Authentication Test on Secured Endpoints
            if op.security:
                test = TestCase(
                    name=f"Invalid Input: {op.method} {op.path} (unauthenticated)",
                    test_type="invalid_input",
                    mutation_type="missing_authentication",
                    operation_key=op_key,
                    method=op.method,
                    path_template=op.path,
                    path_params={"order_id": "ord-1"} if "order_id" in op.path else {},
                    json_body=valid_body,
                    as_user=None,  # No token supplied
                    expected_status_codes=[401],
                    description=f"Send request to secured endpoint without Bearer token and expect HTTP 401.",
                )
                tests.append(test)

        return tests


# ------------------------------------------------------------------------------
# Test Runner & Evaluation Engine
# ------------------------------------------------------------------------------

class TestRunner:
    """Executes generated test cases and dependent sequences against an API."""

    __test__ = False  # Prevent pytest from collecting this class as a test suite

    def __init__(self, executor: RequestExecutor):
        self.executor: RequestExecutor = executor

    def run_test(self, test: TestCase) -> TestResult:
        """Execute a single test case, compare response against expectations, and report status."""
        logger.debug("Running test: %s", test.name)

        # Auto-authenticate user if test specifies as_user and token not yet acquired
        if test.as_user and not test.auth_token:
            if not self.executor.get_user_token(test.as_user):
                pwd = "alice123" if test.as_user.lower() == "alice" else "bob123"
                login_res = self.executor.post(
                    "/auth/login",
                    json_body={"username": test.as_user, "password": pwd},
                )
                if login_res.is_success and login_res.response and login_res.response.is_json:
                    token = login_res.response.body.get("access_token")
                    if token:
                        self.executor.set_user_token(test.as_user, token)

        # Execute HTTP request
        exec_result = self.executor.execute(
            method=test.method,
            path=test.path_template,
            path_params=test.path_params,
            query_params=test.query_params,
            headers=test.headers,
            json_body=test.json_body,
            auth_token=test.auth_token,
            as_user=test.as_user,
        )

        # Evaluate outcome
        if exec_result.has_error:
            return TestResult(
                test_case=test,
                execution_result=exec_result,
                status="ERROR",
                reason=f"Execution error: {exec_result.error_type} ({exec_result.error_message})",
            )

        actual_status = exec_result.status_code
        if actual_status in test.expected_status_codes:
            return TestResult(
                test_case=test,
                execution_result=exec_result,
                status="PASSED",
                reason=f"Received expected status HTTP {actual_status} (expected {test.expected_status_codes}).",
            )

        return TestResult(
            test_case=test,
            execution_result=exec_result,
            status="FAILED",
            reason=(
                f"Status mismatch: received HTTP {actual_status}, but expected {test.expected_status_codes}."
            ),
        )

    def run_tests(self, tests: List[TestCase]) -> List[TestResult]:
        """Execute a list of independent test cases and collect results."""
        return [self.run_test(t) for t in tests]

    # --------------------------------------------------------------------------
    # Dependent Sequence Execution
    # --------------------------------------------------------------------------

    def run_sequence(
        self,
        plan: SequencePlan,
        initial_user: str = "alice",
    ) -> SequenceResult:
        """Execute an ordered sequence plan, passing captured tokens and IDs to subsequent steps."""
        context: Dict[str, Any] = {"user": initial_user}
        step_results: List[TestResult] = []
        all_passed = True

        logger.info("Executing sequence: %s (%d steps)", plan.name, len(plan.steps))

        for step in plan.steps:
            op = step.operation
            path_params: Dict[str, Any] = {}
            body: Optional[Any] = None
            auth_token = context.get("access_token")

            # 1. Resolve inputs from previous steps via dependency relations
            for dep in step.dependencies:
                # Check if we have source field in context
                if dep.source_field in context:
                    val = context[dep.source_field]
                    if dep.target_location == "auth_token":
                        auth_token = val
                    elif dep.target_location == "path_params":
                        path_params[dep.target_field] = val

            # 2. Formulate payload if needed
            if op.method == "POST":
                if "login" in op.path.lower():
                    # Login payload
                    pwd = "alice123" if initial_user == "alice" else "bob123"
                    body = {"username": initial_user, "password": pwd}
                else:
                    body = SchemaSynthesizer.generate_valid_body(op.request_body)

            # Fallback for path params if not supplied by dependency
            for p in op.parameters:
                if p.location == "path" and p.name not in path_params:
                    path_params[p.name] = context.get("id", "ord-1")

            # Determine expected status code
            expected_codes = [
                int(c) for c in op.responses.keys() if c.isdigit() and c.startswith("2")
            ] or [200]

            test_case = TestCase(
                name=f"Step {step.step_index}: {step.operation_key}",
                test_type="sequence_step",
                operation_key=step.operation_key,
                method=op.method,
                path_template=op.path,
                path_params=path_params,
                json_body=body,
                auth_token=auth_token,
                as_user=None if auth_token else (initial_user if op.security else None),
                expected_status_codes=expected_codes,
                description=f"Sequence step {step.step_index} of {plan.name}",
            )

            result = self.run_test(test_case)
            step_results.append(result)

            if not result.is_passed:
                all_passed = False
                logger.warning("Sequence step %d failed: %s", step.step_index, result.reason)
                break  # Stop sequence if a dependency fails

            # 3. Capture response data into context for downstream steps
            if result.execution_result.response and result.execution_result.response.is_json:
                resp_body = result.execution_result.response.body
                if isinstance(resp_body, dict):
                    for k, v in resp_body.items():
                        context[k] = v

        return SequenceResult(
            plan_name=plan.name,
            target_operation=plan.target_operation_key,
            step_results=step_results,
            context_values=context,
            all_passed=all_passed,
        )


# ------------------------------------------------------------------------------
# Schemathesis Baseline Integration
# ------------------------------------------------------------------------------

def run_schemathesis_baseline(
    spec_or_path: Union[str, Dict[str, Any]],
    base_url: str = "http://127.0.0.1:8000",
    max_test_cases: int = 5,
) -> Dict[str, Any]:
    """Run Schemathesis property-based test cases against the OpenAPI target.

    Clearly tags all test cases with [SCHEMATHESIS] to differentiate from agent-generated tests.
    """
    try:
        import schemathesis
    except ImportError:
        return {
            "source": "schemathesis",
            "available": False,
            "message": "schemathesis is not installed.",
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
        }

    logger.info("Initializing Schemathesis baseline run against %s", base_url)

    schema: Any
    if isinstance(spec_or_path, dict):
        schema = schemathesis.openapi.from_dict(spec_or_path)
    elif str(spec_or_path).startswith("http://") or str(spec_or_path).startswith("https://"):
        schema = schemathesis.openapi.from_url(str(spec_or_path))
    else:
        schema = schemathesis.openapi.from_path(str(spec_or_path))

    # Set target base_url in Schemathesis config
    schema.config.update(base_url=base_url)

    passed_count = 0
    failed_count = 0
    records: List[Dict[str, Any]] = []

    # Run property-based checks on endpoints
    for op_res in schema.get_all_operations():
        if hasattr(op_res, "is_ok") and not op_res.is_ok:
            continue
        operation = op_res.ok() if hasattr(op_res, "ok") else op_res

        for idx in range(max_test_cases):
            try:
                case = schema.make_case(operation=operation)
                response = case.call()
                is_ok = response.status_code < 500  # Baseline check: no unhandled 500 server crash
                if is_ok:
                    passed_count += 1
                else:
                    failed_count += 1

                records.append({
                    "tag": "[SCHEMATHESIS]",
                    "method": case.method,
                    "path": case.formatted_path,
                    "status_code": response.status_code,
                    "passed": is_ok,
                })
                break
            except Exception as exc:
                failed_count += 1
                records.append({
                    "tag": "[SCHEMATHESIS]",
                    "method": getattr(operation, "method", "UNKNOWN"),
                    "path": getattr(operation, "path", "/"),
                    "error": str(exc),
                    "passed": False,
                })
                break

    return {
        "source": "schemathesis",
        "available": True,
        "total_tests": passed_count + failed_count,
        "passed": passed_count,
        "failed": failed_count,
        "cases": records,
    }


# ------------------------------------------------------------------------------
# Quick CLI Interface for Testing & Inspection
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from agent.spec_reader import OpenAPISpecReader

    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    spec_path = "sample_api/openapi.json"

    print(f"\n=======================================================")
    print(f"Autonomous AI Testing Agent - Step 4 Test Generation")
    print(f"Target Base URL: {base_url}")
    print(f"=======================================================\n")

    spec = OpenAPISpecReader.load(spec_path)
    executor = RequestExecutor(base_url=base_url)
    generator = TestGenerator(spec)
    runner = TestRunner(executor)

    # 1. Normal Tests
    normal_tests = generator.generate_normal_tests()
    print(f"--> Generated {len(normal_tests)} Normal Tests:")
    for t in normal_tests:
        print(f"    * {t.name} (expecting {t.expected_status_codes})")

    # 2. Invalid-Input Tests
    invalid_tests = generator.generate_invalid_input_tests()
    print(f"\n--> Generated {len(invalid_tests)} Invalid-Input Tests:")
    for t in invalid_tests[:8]:
        print(f"    * {t.name} (expecting {t.expected_status_codes})")
    if len(invalid_tests) > 8:
        print(f"    ... and {len(invalid_tests) - 8} more invalid-input test cases.")

    # 3. Dependent Sequence Execution
    print(f"\n--> Executing Dependent Sequence: Login -> Create Order -> Retrieve Order")
    plan = generator.dep_graph.build_sequence_plan("GET /orders/{order_id}")
    seq_result = runner.run_sequence(plan, initial_user="alice")
    print(seq_result.summary())
    for r in seq_result.step_results:
        print(f"    {r.summary()}")

    print("\nEnd-to-end test generation demonstration completed successfully!\n")
