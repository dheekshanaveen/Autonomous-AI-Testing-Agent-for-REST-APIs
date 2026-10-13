"""HTTP Request Executor for Autonomous AI Testing Agent.

Sends HTTP requests against target REST APIs, formats parameters, manages Bearer
authentication, redacts sensitive credentials from traces, and records detailed
execution metrics and responses without crashing on connection failures.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Union

import httpx
from pydantic import BaseModel, Field

# Setup module logger
logger = logging.getLogger("agent.executor")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(levelname)s] %(asctime)s - %(name)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


# ------------------------------------------------------------------------------
# Sensitive Data Redaction
# ------------------------------------------------------------------------------

SENSITIVE_HEADER_KEYS: Set[str] = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api-key",
    "token",
    "secret",
}

SENSITIVE_BODY_KEYS: Set[str] = {
    "password",
    "passwd",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "client_secret",
    "private_key",
    "api_key",
}


def redact_headers(headers: Optional[Dict[str, str]]) -> Dict[str, str]:
    """Return a copy of headers with sensitive values redacted."""
    if not headers:
        return {}
    clean: Dict[str, str] = {}
    for key, value in headers.items():
        key_lower = key.lower()
        if key_lower in SENSITIVE_HEADER_KEYS:
            if key_lower == "authorization" and value.lower().startswith("bearer "):
                clean[key] = "Bearer [REDACTED]"
            else:
                clean[key] = "[REDACTED]"
        else:
            clean[key] = value
    return clean


def redact_payload(data: Any) -> Any:
    """Recursively redact sensitive field values from dictionaries and lists."""
    if isinstance(data, dict):
        clean_dict: Dict[str, Any] = {}
        for k, v in data.items():
            if isinstance(k, str) and k.lower() in SENSITIVE_BODY_KEYS:
                clean_dict[k] = "[REDACTED]"
            else:
                clean_dict[k] = redact_payload(v)
        return clean_dict
    elif isinstance(data, list):
        return [redact_payload(item) for item in data]
    return data


# ------------------------------------------------------------------------------
# Structured Tracing Models
# ------------------------------------------------------------------------------

class RequestTrace(BaseModel):
    """Structured capture of an outbound HTTP request."""

    method: str = Field(..., description="HTTP Method (GET, POST, etc.)")
    url: str = Field(..., description="Fully resolved target URL")
    path_template: str = Field(..., description="Original path template before substitution")
    path_params: Dict[str, Any] = Field(default_factory=dict, description="Parameters substituted into the URL path")
    query_params: Dict[str, Any] = Field(default_factory=dict, description="Query string parameters")
    headers: Dict[str, str] = Field(default_factory=dict, description="Redacted request headers")
    body: Optional[Any] = Field(default=None, description="Redacted request payload")


class ResponseTrace(BaseModel):
    """Structured capture of an inbound HTTP response."""

    status_code: int = Field(..., description="HTTP response status code")
    headers: Dict[str, str] = Field(default_factory=dict, description="Response headers")
    body: Optional[Any] = Field(default=None, description="Parsed JSON body if available, else raw text")
    is_json: bool = Field(default=False, description="Whether the response was valid JSON")
    text: str = Field(default="", description="Raw response text")


class ExecutionResult(BaseModel):
    """Complete record of a test request execution, including timing and error details."""

    request: RequestTrace = Field(..., description="Details of the outbound request")
    response: Optional[ResponseTrace] = Field(default=None, description="Response details if received")
    duration_ms: float = Field(default=0.0, description="Elapsed execution time in milliseconds")
    has_error: bool = Field(default=False, description="Whether a network/protocol error occurred")
    error_type: Optional[str] = Field(default=None, description="Class name of error if failed")
    error_message: Optional[str] = Field(default=None, description="Error message description")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 execution timestamp",
    )

    @property
    def is_success(self) -> bool:
        """True if the HTTP request completed and returned a 2xx status code."""
        if self.has_error or self.response is None:
            return False
        return 200 <= self.response.status_code < 300

    @property
    def status_code(self) -> Optional[int]:
        """Convenience property for HTTP status code."""
        return self.response.status_code if self.response else None

    def summary(self) -> str:
        """Return a human-readable one-line summary of the execution."""
        if self.has_error:
            return (
                f"[{self.request.method}] {self.request.url} -> ERROR: {self.error_type} "
                f"({self.error_message}) [{self.duration_ms:.1f}ms]"
            )
        status = self.response.status_code if self.response else "NO_RESPONSE"
        return f"[{self.request.method}] {self.request.url} -> HTTP {status} [{self.duration_ms:.1f}ms]"


# ------------------------------------------------------------------------------
# Request Executor Implementation
# ------------------------------------------------------------------------------

class RequestExecutor:
    """HTTP client and execution engine for automated API testing."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        default_timeout: float = 10.0,
        default_headers: Optional[Dict[str, str]] = None,
        custom_client: Optional[httpx.Client] = None,
    ):
        self.base_url: str = base_url.rstrip("/")
        self.default_timeout: float = default_timeout
        self.default_headers: Dict[str, str] = default_headers or {}
        self._user_tokens: Dict[str, str] = {}
        self._custom_client: Optional[httpx.Client] = custom_client

    # --------------------------------------------------------------------------
    # Path & URL Formatting
    # --------------------------------------------------------------------------

    @staticmethod
    def format_path(path_template: str, path_params: Optional[Dict[str, Any]] = None) -> str:
        """Substitute path parameter placeholders (e.g. {order_id}) with supplied values.

        Raises ValueError if a required placeholder in the path is missing from path_params.
        """
        if not path_params:
            path_params = {}

        # Find all placeholders like {order_id} or {user_id}
        placeholders = re.findall(r"\{([a-zA-Z0-9_]+)\}", path_template)
        resolved_path = path_template

        for key in placeholders:
            if key not in path_params:
                raise ValueError(
                    f"Missing required path parameter '{key}' for path template '{path_template}'."
                )
            val = path_params[key]
            # URL-encode value safely
            encoded_val = urllib.parse.quote(str(val), safe="")
            resolved_path = resolved_path.replace(f"{{{key}}}", encoded_val)

        return resolved_path

    def build_url(self, path: str, path_params: Optional[Dict[str, Any]] = None) -> str:
        """Construct a full URL by joining base_url with the formatted path."""
        resolved_path = self.format_path(path, path_params)
        if not resolved_path.startswith("/"):
            resolved_path = f"/{resolved_path}"
        return f"{self.base_url}{resolved_path}"

    # --------------------------------------------------------------------------
    # User Token Management
    # --------------------------------------------------------------------------

    def set_user_token(self, username: str, token: str) -> None:
        """Store an authentication token for a user (e.g. 'alice' or 'bob')."""
        self._user_tokens[username.lower()] = token

    def get_user_token(self, username: str) -> Optional[str]:
        """Retrieve a stored token for a user."""
        return self._user_tokens.get(username.lower())

    def clear_tokens(self) -> None:
        """Clear all cached user tokens."""
        self._user_tokens.clear()

    # --------------------------------------------------------------------------
    # Core Request Execution
    # --------------------------------------------------------------------------

    def execute(
        self,
        method: str,
        path: str,
        path_params: Optional[Dict[str, Any]] = None,
        query_params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        json_body: Optional[Any] = None,
        auth_token: Optional[str] = None,
        as_user: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> ExecutionResult:
        """Send an HTTP request, record the response trace, and capture any network errors.

        Parameters:
            method: HTTP verb (GET, POST, PUT, DELETE, PATCH, etc.)
            path: Target endpoint path or template (e.g. '/orders/{order_id}')
            path_params: Dictionary of path parameters to substitute
            query_params: Query string parameters
            headers: Custom request headers
            json_body: JSON-serializable request body payload
            auth_token: Optional Bearer token to include in Authorization header
            as_user: Look up a stored token for this user ('alice' or 'bob') if auth_token is not given
            timeout: Request timeout in seconds (defaults to self.default_timeout)
        """
        method_upper = method.upper()
        req_timeout = timeout if timeout is not None else self.default_timeout

        # Resolve full URL
        try:
            full_url = self.build_url(path, path_params)
        except ValueError as err:
            # Return an execution result capturing the formatting error without crashing
            req_trace = RequestTrace(
                method=method_upper,
                url=f"{self.base_url}{path}",
                path_template=path,
                path_params=path_params or {},
                query_params=query_params or {},
                headers=redact_headers(headers),
                body=redact_payload(json_body),
            )
            return ExecutionResult(
                request=req_trace,
                has_error=True,
                error_type="ParameterError",
                error_message=str(err),
            )

        # Merge headers
        merged_headers: Dict[str, str] = {**self.default_headers}
        if headers:
            merged_headers.update(headers)

        # Handle authentication token resolution
        effective_token = auth_token
        if not effective_token and as_user:
            effective_token = self.get_user_token(as_user)

        if effective_token:
            merged_headers["Authorization"] = f"Bearer {effective_token}"

        # Build redacted request trace for logging and result storage
        redacted_request_headers = redact_headers(merged_headers)
        redacted_request_body = redact_payload(json_body)

        request_trace = RequestTrace(
            method=method_upper,
            url=full_url,
            path_template=path,
            path_params=path_params or {},
            query_params=query_params or {},
            headers=redacted_request_headers,
            body=redacted_request_body,
        )

        logger.debug(
            "Executing request: %s %s (params: %s)",
            method_upper,
            full_url,
            query_params,
        )

        start_time = time.perf_counter()
        response_trace: Optional[ResponseTrace] = None
        has_error = False
        error_type: Optional[str] = None
        error_message: Optional[str] = None

        # Execute HTTP call via httpx
        try:
            client = self._custom_client or httpx.Client(timeout=req_timeout)
            try:
                raw_response = client.request(
                    method=method_upper,
                    url=full_url,
                    params=query_params,
                    headers=merged_headers,
                    json=json_body,
                )

                # Parse response body
                body_content: Any = None
                is_json = False
                try:
                    body_content = raw_response.json()
                    is_json = True
                except Exception:
                    body_content = raw_response.text

                response_trace = ResponseTrace(
                    status_code=raw_response.status_code,
                    headers=dict(raw_response.headers),
                    body=body_content,
                    is_json=is_json,
                    text=raw_response.text,
                )
            finally:
                if self._custom_client is None:
                    client.close()

        except httpx.ConnectError as exc:
            has_error = True
            error_type = "ConnectionError"
            error_message = f"Failed to connect to '{full_url}': {exc}"
            logger.warning("Connection failure during %s %s: %s", method_upper, full_url, exc)

        except httpx.TimeoutException as exc:
            has_error = True
            error_type = "TimeoutError"
            error_message = f"Request to '{full_url}' timed out after {req_timeout}s."
            logger.warning("Timeout during %s %s", method_upper, full_url)

        except httpx.RequestError as exc:
            has_error = True
            error_type = "RequestError"
            error_message = f"HTTP request error: {exc}"
            logger.warning("HTTP request error during %s %s: %s", method_upper, full_url, exc)

        except Exception as exc:
            has_error = True
            error_type = type(exc).__name__
            error_message = str(exc)
            logger.error("Unexpected error during %s %s: %s", method_upper, full_url, exc)

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        result = ExecutionResult(
            request=request_trace,
            response=response_trace,
            duration_ms=round(elapsed_ms, 2),
            has_error=has_error,
            error_type=error_type,
            error_message=error_message,
        )

        logger.info(result.summary())
        return result

    # --------------------------------------------------------------------------
    # Convenience HTTP Methods
    # --------------------------------------------------------------------------

    def get(
        self,
        path: str,
        path_params: Optional[Dict[str, Any]] = None,
        query_params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        auth_token: Optional[str] = None,
        as_user: Optional[str] = None,
    ) -> ExecutionResult:
        """Send a GET request."""
        return self.execute(
            method="GET",
            path=path,
            path_params=path_params,
            query_params=query_params,
            headers=headers,
            auth_token=auth_token,
            as_user=as_user,
        )

    def post(
        self,
        path: str,
        json_body: Optional[Any] = None,
        path_params: Optional[Dict[str, Any]] = None,
        query_params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        auth_token: Optional[str] = None,
        as_user: Optional[str] = None,
    ) -> ExecutionResult:
        """Send a POST request."""
        return self.execute(
            method="POST",
            path=path,
            json_body=json_body,
            path_params=path_params,
            query_params=query_params,
            headers=headers,
            auth_token=auth_token,
            as_user=as_user,
        )

    def put(
        self,
        path: str,
        json_body: Optional[Any] = None,
        path_params: Optional[Dict[str, Any]] = None,
        query_params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        auth_token: Optional[str] = None,
        as_user: Optional[str] = None,
    ) -> ExecutionResult:
        """Send a PUT request."""
        return self.execute(
            method="PUT",
            path=path,
            json_body=json_body,
            path_params=path_params,
            query_params=query_params,
            headers=headers,
            auth_token=auth_token,
            as_user=as_user,
        )

    def patch(
        self,
        path: str,
        json_body: Optional[Any] = None,
        path_params: Optional[Dict[str, Any]] = None,
        query_params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        auth_token: Optional[str] = None,
        as_user: Optional[str] = None,
    ) -> ExecutionResult:
        """Send a PATCH request."""
        return self.execute(
            method="PATCH",
            path=path,
            json_body=json_body,
            path_params=path_params,
            query_params=query_params,
            headers=headers,
            auth_token=auth_token,
            as_user=as_user,
        )

    def delete(
        self,
        path: str,
        path_params: Optional[Dict[str, Any]] = None,
        query_params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        auth_token: Optional[str] = None,
        as_user: Optional[str] = None,
    ) -> ExecutionResult:
        """Send a DELETE request."""
        return self.execute(
            method="DELETE",
            path=path,
            path_params=path_params,
            query_params=query_params,
            headers=headers,
            auth_token=auth_token,
            as_user=as_user,
        )


# ------------------------------------------------------------------------------
# Quick CLI Interface for Testing & Inspection
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    executor = RequestExecutor(base_url=base)

    print(f"\n--- Testing API Request Executor against: {base} ---")

    # 1. Health check
    health_res = executor.get("/health")
    print(f"Health Check: {health_res.summary()}")

    # 2. Login as Alice
    login_res = executor.post(
        "/auth/login",
        json_body={"username": "alice", "password": "alice123"},
    )
    print(f"Alice Login: {login_res.summary()}")

    if login_res.is_success and login_res.response and login_res.response.is_json:
        token = login_res.response.body.get("access_token")
        executor.set_user_token("alice", token)

        # 3. Create order
        order_res = executor.post(
            "/orders",
            json_body={"item_name": "Mechanical Keyboard", "quantity": 1, "total_price": 89.99},
            as_user="alice",
        )
        print(f"Create Order: {order_res.summary()}")

        if order_res.is_success and order_res.response and order_res.response.is_json:
            order_id = order_res.response.body.get("id")

            # 4. Retrieve order using path_params substitution
            get_order_res = executor.get(
                "/orders/{order_id}",
                path_params={"order_id": order_id},
                as_user="alice",
            )
            print(f"Retrieve Order: {get_order_res.summary()}")
            print("\nRetrieved Order Data:")
            print(json.dumps(get_order_res.response.body, indent=2))

    print("\nExecutor verification completed.\n")
