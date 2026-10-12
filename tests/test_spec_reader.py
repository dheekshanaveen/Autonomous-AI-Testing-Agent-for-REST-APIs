"""Comprehensive unit and integration tests for the OpenAPI Specification Reader."""

import json
from pathlib import Path
import pytest
import httpx

from agent.spec_reader import (
    OpenAPISpecReader,
    APISpecification,
    SpecReaderError,
    SpecConnectionError,
    SpecNotFoundError,
    SpecParseError,
    SpecValidationError,
    SpecResolutionError,
)
from sample_api.main import app


# ------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------

@pytest.fixture
def sample_spec_dict():
    """Return the live sample API's OpenAPI specification dictionary."""
    return app.openapi()


@pytest.fixture
def sample_spec_file(tmp_path, sample_spec_dict):
    """Save the sample OpenAPI spec to a temporary file."""
    file_path = tmp_path / "openapi_test.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(sample_spec_dict, f)
    return file_path


# ------------------------------------------------------------------------------
# Loading & Endpoint Discovery Tests
# ------------------------------------------------------------------------------

def test_load_from_dict(sample_spec_dict):
    """Verify loading and parsing the spec from an in-memory dictionary."""
    spec = OpenAPISpecReader.load_from_dict(sample_spec_dict)
    assert isinstance(spec, APISpecification)
    assert "Sample Shopping API" in spec.title
    assert spec.openapi_version == "3.1.0"
    assert spec.version == "1.0.0"


def test_discover_expected_endpoints(sample_spec_dict):
    """Verify discovery of all required sample API endpoints."""
    spec = OpenAPISpecReader.load_from_dict(sample_spec_dict)
    expected_endpoints = {
        "/health",
        "/auth/login",
        "/orders",
        "/orders/{order_id}",
        "/admin/reset",
    }
    assert expected_endpoints.issubset(set(spec.endpoints))
    assert len(spec.operations) == 5


def test_load_from_file(sample_spec_file):
    """Verify loading the spec from a saved JSON file."""
    spec = OpenAPISpecReader.load_from_file(sample_spec_file)
    assert isinstance(spec, APISpecification)
    assert len(spec.endpoints) >= 5
    assert "/orders/{order_id}" in spec.endpoints


def test_universal_loader(sample_spec_file, sample_spec_dict):
    """Verify the universal loader handles dicts and file paths interchangeably."""
    spec1 = OpenAPISpecReader.load(sample_spec_dict)
    assert spec1.title == "Sample Shopping API (Controlled Vulnerable Target)"

    spec2 = OpenAPISpecReader.load(str(sample_spec_file))
    assert spec2.title == spec1.title


# ------------------------------------------------------------------------------
# Operation, Parameter, Request Body & Response Tests
# ------------------------------------------------------------------------------

def test_parameter_extraction(sample_spec_dict):
    """Verify path parameter extraction on GET /orders/{order_id}."""
    spec = OpenAPISpecReader.load_from_dict(sample_spec_dict)
    op = spec.get_operation("GET", "/orders/{order_id}")
    assert op is not None
    assert len(op.parameters) == 1

    param = op.parameters[0]
    assert param.name == "order_id"
    assert param.location == "path"
    assert param.required is True
    assert param.schema_info is not None
    assert param.schema_info.get("type") == "string"


def test_request_body_extraction(sample_spec_dict):
    """Verify request body schemas for /auth/login and /orders."""
    spec = OpenAPISpecReader.load_from_dict(sample_spec_dict)

    # /auth/login
    login_op = spec.get_operation("POST", "/auth/login")
    assert login_op is not None
    assert login_op.request_body is not None
    assert login_op.request_body.required is True
    assert "application/json" in login_op.request_body.content_types

    login_schema = login_op.request_body.schemas["application/json"]
    assert "properties" in login_schema
    assert "username" in login_schema["properties"]
    assert "password" in login_schema["properties"]
    assert "required" in login_schema
    assert "username" in login_schema["required"]

    # /orders
    orders_op = spec.get_operation("POST", "/orders")
    assert orders_op is not None
    assert orders_op.request_body is not None
    order_schema = orders_op.request_body.schemas["application/json"]
    assert "item_name" in order_schema["properties"]
    assert "quantity" in order_schema["properties"]
    assert "total_price" in order_schema["properties"]


def test_response_extraction_and_ref_resolution(sample_spec_dict):
    """Verify response extraction and full $ref resolution on responses."""
    spec = OpenAPISpecReader.load_from_dict(sample_spec_dict)
    op = spec.get_operation("GET", "/orders/{order_id}")
    assert op is not None

    # Check 200 response
    assert "200" in op.responses
    resp_200 = op.responses["200"]
    assert "application/json" in resp_200.content_types

    # Ensure $ref was resolved to actual OrderResponse schema
    schema = resp_200.schemas["application/json"]
    assert "properties" in schema
    assert "id" in schema["properties"]
    assert "user_id" in schema["properties"]
    assert "item_name" in schema["properties"]
    assert "total_price" in schema["properties"]


# ------------------------------------------------------------------------------
# Authentication & Security Requirements Tests
# ------------------------------------------------------------------------------

def test_security_schemes_and_operation_requirements(sample_spec_dict):
    """Verify identification of Bearer security scheme and protected endpoints."""
    spec = OpenAPISpecReader.load_from_dict(sample_spec_dict)

    # Security schemes
    assert "HTTPBearer" in spec.security_schemes
    scheme = spec.security_schemes["HTTPBearer"]
    assert scheme.type == "http"
    assert scheme.scheme == "bearer"

    # Protected operations
    orders_post = spec.get_operation("POST", "/orders")
    assert len(orders_post.security) == 1
    assert orders_post.security[0].scheme_name == "HTTPBearer"

    orders_get = spec.get_operation("GET", "/orders/{order_id}")
    assert len(orders_get.security) == 1
    assert orders_get.security[0].scheme_name == "HTTPBearer"

    # Public operations
    health_op = spec.get_operation("GET", "/health")
    assert len(health_op.security) == 0

    login_op = spec.get_operation("POST", "/auth/login")
    assert len(login_op.security) == 0

    # Helper method
    protected_ops = spec.get_operations_requiring_auth()
    protected_paths = {op.path for op in protected_ops}
    assert protected_paths == {"/orders", "/orders/{order_id}"}


# ------------------------------------------------------------------------------
# Explicit Links & Dependency Information Tests
# ------------------------------------------------------------------------------

def test_explicit_links_extraction():
    """Verify extraction of explicit OpenAPI response links (dependencies)."""
    spec_with_links = {
        "openapi": "3.1.0",
        "info": {"title": "Linked API", "version": "1.0.0"},
        "paths": {
            "/users": {
                "post": {
                    "operationId": "createUser",
                    "responses": {
                        "201": {
                            "description": "User created",
                            "links": {
                                "GetUserById": {
                                    "operationId": "getUserById",
                                    "parameters": {"userId": "$response.body#/id"},
                                }
                            },
                        }
                    },
                }
            },
            "/users/{userId}": {
                "get": {
                    "operationId": "getUserById",
                    "parameters": [{"name": "userId", "in": "path", "required": True}],
                    "responses": {"200": {"description": "User details"}},
                }
            },
        },
    }
    spec = OpenAPISpecReader.load_from_dict(spec_with_links)
    create_op = spec.get_operation("POST", "/users")
    assert create_op is not None
    assert "201.GetUserById" in create_op.links
    assert create_op.links["201.GetUserById"]["operationId"] == "getUserById"
    assert create_op.links["201.GetUserById"]["parameters"]["userId"] == "$response.body#/id"


# ------------------------------------------------------------------------------
# Error Handling Tests
# ------------------------------------------------------------------------------

def test_missing_file_raises_not_found(tmp_path):
    """Verify SpecNotFoundError when opening a non-existent file."""
    non_existent = tmp_path / "does_not_exist.json"
    with pytest.raises(SpecNotFoundError) as exc_info:
        OpenAPISpecReader.load_from_file(non_existent)
    assert "file not found" in str(exc_info.value).lower()


def test_malformed_json_file_raises_parse_error(tmp_path):
    """Verify SpecParseError when loading corrupt JSON."""
    corrupt_file = tmp_path / "corrupt.json"
    corrupt_file.write_text("{ unquoted_key: 123 ", encoding="utf-8")
    with pytest.raises(SpecParseError) as exc_info:
        OpenAPISpecReader.load_from_file(corrupt_file)
    assert "malformed json" in str(exc_info.value).lower()


def test_invalid_openapi_structure_missing_paths():
    """Verify SpecValidationError when 'paths' is absent."""
    invalid_spec = {"openapi": "3.1.0", "info": {"title": "Bad", "version": "1.0"}}
    with pytest.raises(SpecValidationError) as exc_info:
        OpenAPISpecReader.load_from_dict(invalid_spec)
    assert "missing the required 'paths' object" in str(exc_info.value).lower()


def test_unsupported_openapi_version():
    """Verify SpecValidationError when OpenAPI version is not 3.x."""
    swagger_spec = {"openapi": "2.0", "paths": {}}
    with pytest.raises(SpecValidationError) as exc_info:
        OpenAPISpecReader.load_from_dict(swagger_spec)
    assert "unsupported openapi version '2.0'" in str(exc_info.value).lower()


def test_missing_component_ref_raises_resolution_error():
    """Verify SpecResolutionError when $ref points to a missing component."""
    broken_ref_spec = {
        "openapi": "3.1.0",
        "info": {"title": "Broken Ref API", "version": "1.0.0"},
        "paths": {
            "/items": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/NonExistent"}
                                }
                            },
                        }
                    }
                }
            }
        },
    }
    with pytest.raises(SpecResolutionError) as exc_info:
        OpenAPISpecReader.load_from_dict(broken_ref_spec)
    assert "could not be resolved" in str(exc_info.value).lower()
    assert "NonExistent" in str(exc_info.value)


def test_circular_ref_handled_gracefully():
    """Verify circular component references do not cause recursion errors."""
    circular_spec = {
        "openapi": "3.1.0",
        "info": {"title": "Circular API", "version": "1.0.0"},
        "paths": {
            "/nodes": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Node"}
                                }
                            },
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "Node": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "parent": {"$ref": "#/components/schemas/Node"},
                    },
                }
            }
        },
    }
    spec = OpenAPISpecReader.load_from_dict(circular_spec)
    node_schema = spec.operations[0].responses["200"].schemas["application/json"]
    assert "properties" in node_schema
    # Parent should be flagged circular rather than causing RecursionError
    parent_prop = node_schema["properties"]["parent"]
    assert parent_prop.get("_circular") is True


def test_server_unavailable_raises_connection_error(monkeypatch):
    """Verify SpecConnectionError when remote server cannot be reached."""
    # Test connection refusal / unreachable
    with pytest.raises(SpecConnectionError) as exc_info:
        OpenAPISpecReader.load_from_url("http://127.0.0.1:59999/openapi.json", timeout=1.0)
    msg = str(exc_info.value).lower()
    assert "failed to connect" in msg or "timed out" in msg or "error" in msg

    # Test explicit ConnectError via monkeypatch for deterministic coverage
    def mock_get(*args, **kwargs):
        raise httpx.ConnectError("Connection refused by peer")

    monkeypatch.setattr(httpx.Client, "get", mock_get)
    with pytest.raises(SpecConnectionError) as exc_info2:
        OpenAPISpecReader.load_from_url("http://example.com/openapi.json")
    assert "failed to connect" in str(exc_info2.value).lower()
