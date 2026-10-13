"""Automated tests for the HTTP Request Executor."""

import json
import httpx
import pytest

from agent.executor import (
    RequestExecutor,
    ExecutionResult,
    redact_headers,
    redact_payload,
)
from sample_api.main import app
from sample_api.database import reset_db
from sample_api.auth import reset_auth


from fastapi.testclient import TestClient

# ------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_state():
    """Ensure clean database and session state for every test."""
    reset_db()
    reset_auth()
    yield
    reset_db()
    reset_auth()


@pytest.fixture
def app_executor():
    """RequestExecutor connected directly to the FastAPI sample application."""
    test_client = TestClient(app, base_url="http://testserver")
    return RequestExecutor(base_url="http://testserver", custom_client=test_client)


# ------------------------------------------------------------------------------
# Core Execution & HTTP Methods Tests
# ------------------------------------------------------------------------------

def test_get_health_request(app_executor: RequestExecutor):
    """GET request to /health executes and records the response properly."""
    result = app_executor.get("/health")
    assert result.has_error is False
    assert result.is_success is True
    assert result.status_code == 200
    assert result.duration_ms > 0

    # Verify response trace
    assert result.response is not None
    assert result.response.is_json is True
    assert result.response.body["status"] == "ok"
    assert "Sample Shopping API" in result.response.body["app"]


def test_post_json_body_login(app_executor: RequestExecutor):
    """POST request transmits a JSON body and records response."""
    result = app_executor.post(
        "/auth/login",
        json_body={"username": "alice", "password": "alice123"},
    )
    assert result.has_error is False
    assert result.status_code == 200
    assert result.response is not None
    assert result.response.is_json is True
    assert "access_token" in result.response.body
    assert result.response.body["user_id"] == "user-alice"


def test_path_parameter_substitution(app_executor: RequestExecutor):
    """Path templates with parameters like /orders/{order_id} are substituted properly."""
    # 1. Login Alice & create order
    login_res = app_executor.post(
        "/auth/login",
        json_body={"username": "alice", "password": "alice123"},
    )
    token = login_res.response.body["access_token"]

    create_res = app_executor.post(
        "/orders",
        json_body={"item_name": "Mechanical Keyboard", "quantity": 1, "total_price": 99.0},
        auth_token=token,
    )
    order_id = create_res.response.body["id"]

    # 2. Retrieve order using path_params
    get_res = app_executor.get(
        "/orders/{order_id}",
        path_params={"order_id": order_id},
        auth_token=token,
    )
    assert get_res.has_error is False
    assert get_res.status_code == 200
    assert get_res.request.url.endswith(f"/orders/{order_id}")
    assert get_res.request.path_params == {"order_id": order_id}
    assert get_res.response.body["id"] == order_id


def test_missing_path_parameter_handled_cleanly(app_executor: RequestExecutor):
    """Missing required path parameter returns an ExecutionResult with ParameterError without crashing."""
    result = app_executor.get("/orders/{order_id}")
    assert result.has_error is True
    assert result.error_type == "ParameterError"
    assert "Missing required path parameter 'order_id'" in result.error_message


def test_query_parameters_handled(app_executor: RequestExecutor):
    """Query parameters are attached and recorded in the request trace."""
    result = app_executor.get("/health", query_params={"env": "testing", "debug": "true"})
    assert result.has_error is False
    assert result.status_code == 200
    assert result.request.query_params == {"env": "testing", "debug": "true"}


# ------------------------------------------------------------------------------
# Authentication Tests
# ------------------------------------------------------------------------------

def test_bearer_token_authentication(app_executor: RequestExecutor):
    """Bearer token authentication works for protected endpoints."""
    # Unauthenticated request rejected
    unauth_res = app_executor.get("/orders/ord-1")
    assert unauth_res.status_code == 401

    # Login and store user token
    login_res = app_executor.post(
        "/auth/login",
        json_body={"username": "alice", "password": "alice123"},
    )
    token = login_res.response.body["access_token"]
    app_executor.set_user_token("alice", token)

    # Execute request as Alice
    auth_res = app_executor.post(
        "/orders",
        json_body={"item_name": "Headphones", "quantity": 1, "total_price": 49.99},
        as_user="alice",
    )
    assert auth_res.status_code == 201
    assert auth_res.response.body["user_id"] == "user-alice"


# ------------------------------------------------------------------------------
# Redaction & Security Logging Tests
# ------------------------------------------------------------------------------

def test_sensitive_header_redaction():
    """Verify Authorization and API keys are redacted from headers."""
    raw_headers = {
        "Authorization": "Bearer super-secret-jwt-token-12345",
        "X-Api-Key": "my-secret-key",
        "Content-Type": "application/json",
        "User-Agent": "TestAgent/1.0",
    }
    redacted = redact_headers(raw_headers)
    assert redacted["Authorization"] == "Bearer [REDACTED]"
    assert redacted["X-Api-Key"] == "[REDACTED]"
    assert redacted["Content-Type"] == "application/json"
    assert redacted["User-Agent"] == "TestAgent/1.0"


def test_sensitive_payload_redaction():
    """Verify passwords, secrets, and tokens are redacted from request bodies."""
    raw_payload = {
        "username": "alice",
        "password": "secret_password",
        "details": {
            "token": "refresh_token_987",
            "nested_count": 5,
        },
    }
    redacted = redact_payload(raw_payload)
    assert redacted["username"] == "alice"
    assert redacted["password"] == "[REDACTED]"
    assert redacted["details"]["token"] == "[REDACTED]"
    assert redacted["details"]["nested_count"] == 5


def test_executor_records_redacted_traces(app_executor: RequestExecutor):
    """The request trace in ExecutionResult must contain redacted headers and payload."""
    login_res = app_executor.post(
        "/auth/login",
        json_body={"username": "alice", "password": "alice123"},
    )
    # Password must be redacted in the stored request trace
    assert login_res.request.body["password"] == "[REDACTED]"
    assert login_res.request.body["username"] == "alice"

    # Authorization header must be redacted in stored request trace
    token = login_res.response.body["access_token"]
    order_res = app_executor.post(
        "/orders",
        json_body={"item_name": "Book", "quantity": 1, "total_price": 15.0},
        auth_token=token,
    )
    assert order_res.request.headers["Authorization"] == "Bearer [REDACTED]"


# ------------------------------------------------------------------------------
# Error Handling Tests (Timeouts, Connection Errors)
# ------------------------------------------------------------------------------

def test_connection_failure_handled_gracefully(monkeypatch):
    """Connection errors are captured cleanly in ExecutionResult without crashing."""
    executor = RequestExecutor(base_url="http://127.0.0.1:59999", default_timeout=1.0)

    def mock_request(*args, **kwargs):
        raise httpx.ConnectError("Connection refused by target")

    monkeypatch.setattr(httpx.Client, "request", mock_request)
    result = executor.get("/health")
    assert result.has_error is True
    assert result.response is None
    assert result.error_type == "ConnectionError"
    assert "Connection refused" in result.error_message


def test_unreachable_server_does_not_crash():
    """Real unreachable host returns network error or timeout cleanly."""
    executor = RequestExecutor(base_url="http://127.0.0.1:59999", default_timeout=0.5)
    result = executor.get("/health")
    assert result.has_error is True
    assert result.response is None
    assert result.error_type in ("ConnectionError", "TimeoutError")


def test_timeout_handled_gracefully(monkeypatch):
    """Timeout during HTTP request returns ExecutionResult with TimeoutError."""
    executor = RequestExecutor(base_url="http://example.com", default_timeout=1.0)

    def mock_request(*args, **kwargs):
        raise httpx.TimeoutException("Operation timed out")

    monkeypatch.setattr(httpx.Client, "request", mock_request)

    result = executor.get("/test")
    assert result.has_error is True
    assert result.response is None
    assert result.error_type == "TimeoutError"
    assert "timed out" in result.error_message.lower()


def test_generic_request_error_handled_gracefully(monkeypatch):
    """Protocol / Request errors are captured cleanly in ExecutionResult."""
    executor = RequestExecutor(base_url="http://example.com")

    def mock_request(*args, **kwargs):
        raise httpx.RequestError("Protocol error")

    monkeypatch.setattr(httpx.Client, "request", mock_request)

    result = executor.get("/test")
    assert result.has_error is True
    assert result.error_type == "RequestError"
