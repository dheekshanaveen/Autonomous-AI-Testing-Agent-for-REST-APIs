"""Automated tests for the automatic test generator and sequence runner."""

import pytest
from fastapi.testclient import TestClient

from agent.spec_reader import OpenAPISpecReader
from agent.executor import RequestExecutor
from agent.dependency_graph import APIDependencyGraph
from agent.test_generator import (
    TestGenerator,
    TestRunner,
    TestCase,
    TestResult,
    SequenceResult,
    run_schemathesis_baseline,
)
from sample_api.main import app
from sample_api.database import reset_db
from sample_api.auth import reset_auth


@pytest.fixture(autouse=True)
def clean_database():
    """Ensure clean database and session state for every test."""
    reset_db()
    reset_auth()
    yield
    reset_db()
    reset_auth()


@pytest.fixture
def sample_spec():
    """Load the sample API specification."""
    return OpenAPISpecReader.load_from_dict(app.openapi())


@pytest.fixture
def app_runner():
    """TestRunner connected directly to the FastAPI sample application."""
    test_client = TestClient(app, base_url="http://testserver")
    executor = RequestExecutor(base_url="http://testserver", custom_client=test_client)
    return TestRunner(executor)


# ------------------------------------------------------------------------------
# Generation Tests
# ------------------------------------------------------------------------------

def test_generate_normal_tests(sample_spec):
    """Verify normal test cases are generated for all operations with valid inputs."""
    generator = TestGenerator(sample_spec)
    normal_tests = generator.generate_normal_tests()

    assert len(normal_tests) == 5
    op_keys = [t.operation_key for t in normal_tests]
    assert "GET /health" in op_keys
    assert "POST /auth/login" in op_keys
    assert "POST /orders" in op_keys
    assert "GET /orders/{order_id}" in op_keys
    assert "POST /admin/reset" in op_keys

    # Check POST /orders normal test details
    order_test = next(t for t in normal_tests if t.operation_key == "POST /orders")
    assert order_test.test_type == "normal"
    assert order_test.json_body is not None
    assert "item_name" in order_test.json_body
    assert "quantity" in order_test.json_body
    assert "total_price" in order_test.json_body
    assert 201 in order_test.expected_status_codes


def test_generate_invalid_input_missing_fields(sample_spec):
    """Verify negative test cases are generated for missing required fields."""
    generator = TestGenerator(sample_spec)
    invalid_tests = generator.generate_invalid_input_tests()

    missing_field_tests = [
        t for t in invalid_tests if t.mutation_type == "missing_required_field"
    ]
    assert len(missing_field_tests) > 0

    # Ensure required fields of /orders (item_name, quantity, total_price) are tested
    order_missing = [t for t in missing_field_tests if t.operation_key == "POST /orders"]
    assert len(order_missing) == 3
    for t in order_missing:
        assert t.expected_status_codes == [400, 422]
        assert t.test_type == "invalid_input"


def test_generate_invalid_input_type_mismatches(sample_spec):
    """Verify negative test cases are generated for type mismatches."""
    generator = TestGenerator(sample_spec)
    invalid_tests = generator.generate_invalid_input_tests()

    type_tests = [t for t in invalid_tests if t.mutation_type == "type_mismatch"]
    assert len(type_tests) > 0
    for t in type_tests:
        assert t.expected_status_codes == [400, 422]


def test_generate_invalid_input_unauthenticated(sample_spec):
    """Secured endpoints must generate an unauthenticated test expecting HTTP 401."""
    generator = TestGenerator(sample_spec)
    invalid_tests = generator.generate_invalid_input_tests()

    unauth_tests = [t for t in invalid_tests if t.mutation_type == "missing_authentication"]
    assert len(unauth_tests) >= 2
    for t in unauth_tests:
        assert t.expected_status_codes == [401]
        assert t.as_user is None
        assert t.auth_token is None


# ------------------------------------------------------------------------------
# Execution & Evaluation Tests
# ------------------------------------------------------------------------------

def test_run_normal_test_passes(sample_spec, app_runner: TestRunner):
    """Executing a valid normal test case against the API results in PASSED."""
    generator = TestGenerator(sample_spec)
    health_test = next(t for t in generator.generate_normal_tests() if t.operation_key == "GET /health")

    result = app_runner.run_test(health_test)
    assert result.status == "PASSED"
    assert result.is_passed is True
    assert result.execution_result.status_code == 200
    assert "Received expected status HTTP 200" in result.reason


def test_run_invalid_input_test_passes(sample_spec, app_runner: TestRunner):
    """When API correctly rejects an invalid payload with 422, test outcome is PASSED."""
    generator = TestGenerator(sample_spec)
    invalid_tests = generator.generate_invalid_input_tests()

    # Missing item_name on POST /orders
    missing_item = next(
        t for t in invalid_tests
        if t.operation_key == "POST /orders" and "missing 'item_name'" in t.name
    )
    result = app_runner.run_test(missing_item)
    assert result.status == "PASSED"
    assert result.execution_result.status_code == 422


def test_run_test_failure_detection(sample_spec, app_runner: TestRunner):
    """When the status code does not match expectations, status is FAILED with details."""
    # Create test expecting 200 on an endpoint that requires auth (unauthenticated returns 401)
    unauth_test = TestCase(
        name="Expect 200 on Protected Endpoint Without Token",
        test_type="normal",
        operation_key="POST /orders",
        method="POST",
        path_template="/orders",
        json_body={"item_name": "Book", "quantity": 1, "total_price": 10.0},
        expected_status_codes=[200, 201],  # Wrong expectation
    )
    result = app_runner.run_test(unauth_test)
    assert result.status == "FAILED"
    assert result.is_passed is False
    assert result.execution_result.status_code == 401
    assert "Status mismatch: received HTTP 401" in result.reason


# ------------------------------------------------------------------------------
# Dependent Sequence Execution Tests
# ------------------------------------------------------------------------------

def test_dependent_sequence_execution(sample_spec, app_runner: TestRunner):
    """Execute Login -> Create Order -> Get Order sequence propagating token and order_id."""
    graph = APIDependencyGraph(sample_spec)
    plan = graph.build_sequence_plan("GET /orders/{order_id}")

    seq_result = app_runner.run_sequence(plan, initial_user="alice")
    assert seq_result.all_passed is True
    assert len(seq_result.step_results) == 3

    # Step 1: Login
    login_step = seq_result.step_results[0]
    assert login_step.status == "PASSED"
    assert "access_token" in seq_result.context_values

    # Step 2: Create Order
    create_step = seq_result.step_results[1]
    assert create_step.status == "PASSED"
    assert "id" in seq_result.context_values
    created_id = seq_result.context_values["id"]

    # Step 3: Retrieve Order
    get_step = seq_result.step_results[2]
    assert get_step.status == "PASSED"
    assert get_step.test_case.path_params["order_id"] == created_id
    assert get_step.execution_result.response.body["id"] == created_id
    assert get_step.execution_result.response.body["user_id"] == "user-alice"


def test_dependent_sequence_handles_step_failure(sample_spec, app_runner: TestRunner):
    """If a step in a sequence fails (e.g. bad credentials), the sequence halts safely."""
    graph = APIDependencyGraph(sample_spec)
    plan = graph.build_sequence_plan("GET /orders/{order_id}")

    # Use unknown user which fails login
    seq_result = app_runner.run_sequence(plan, initial_user="unknown_user")
    assert seq_result.all_passed is False
    # Sequence should halt after failed login step
    assert len(seq_result.step_results) == 1
    assert seq_result.step_results[0].status == "FAILED"


# ------------------------------------------------------------------------------
# Schemathesis Baseline Integration Test
# ------------------------------------------------------------------------------

def test_schemathesis_baseline_runner(sample_spec):
    """Verify Schemathesis runs and tags baseline test records."""
    baseline = run_schemathesis_baseline(
        spec_or_path=sample_spec.raw_spec,
        base_url="http://127.0.0.1:8000",
        max_test_cases=1,
    )
    assert baseline["source"] == "schemathesis"
    assert baseline["available"] is True
    assert "cases" in baseline
    assert all(c["tag"] == "[SCHEMATHESIS]" for c in baseline["cases"])
