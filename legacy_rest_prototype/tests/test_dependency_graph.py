"""Unit tests for the API Dependency Graph module."""

import pytest

from agent.spec_reader import OpenAPISpecReader
from agent.dependency_graph import (
    APIDependencyGraph,
    DependencyRelation,
    SequencePlan,
)
from sample_api.main import app


@pytest.fixture
def sample_spec():
    """Load the sample shopping API specification."""
    return OpenAPISpecReader.load_from_dict(app.openapi())


def test_dependency_graph_nodes(sample_spec):
    """Verify all operations are registered as nodes in the graph."""
    graph = APIDependencyGraph(sample_spec)
    expected_nodes = {
        "GET /health",
        "POST /auth/login",
        "POST /orders",
        "GET /orders/{order_id}",
        "POST /admin/reset",
    }
    assert set(graph.graph.nodes()).issubset(expected_nodes) or expected_nodes.issubset(set(graph.graph.nodes()))
    assert len(graph.graph.nodes()) == 5


def test_auth_dependency_discovery(sample_spec):
    """Secured endpoints must depend on POST /auth/login for token generation."""
    graph = APIDependencyGraph(sample_spec)
    deps_for_orders = graph.get_dependencies_for("POST /orders")
    assert any(d.producer_key == "POST /auth/login" and d.target_location == "auth_token" for d in deps_for_orders)

    deps_for_get_order = graph.get_dependencies_for("GET /orders/{order_id}")
    assert any(d.producer_key == "POST /auth/login" and d.target_location == "auth_token" for d in deps_for_get_order)


def test_path_parameter_dependency_discovery(sample_spec):
    """GET /orders/{order_id} must depend on POST /orders to provide the order_id."""
    graph = APIDependencyGraph(sample_spec)
    deps = graph.get_dependencies_for("GET /orders/{order_id}")
    order_id_dep = next((d for d in deps if d.target_field == "order_id"), None)

    assert order_id_dep is not None
    assert order_id_dep.producer_key == "POST /orders"
    assert order_id_dep.source_field == "id"
    assert order_id_dep.target_location == "path_params"


def test_build_sequence_plan_for_dependent_endpoint(sample_spec):
    """Generating a plan for GET /orders/{order_id} should order: Login -> Create Order -> Get Order."""
    graph = APIDependencyGraph(sample_spec)
    plan = graph.build_sequence_plan("GET /orders/{order_id}")

    assert isinstance(plan, SequencePlan)
    assert plan.target_operation_key == "GET /orders/{order_id}"
    assert len(plan.steps) == 3

    keys = plan.operation_keys
    assert keys[0] == "POST /auth/login"
    assert keys[1] == "POST /orders"
    assert keys[2] == "GET /orders/{order_id}"


def test_sequence_plan_for_independent_endpoint(sample_spec):
    """GET /health has no dependencies and should produce a single-step plan."""
    graph = APIDependencyGraph(sample_spec)
    plan = graph.build_sequence_plan("GET /health")
    assert len(plan.steps) == 1
    assert plan.steps[0].operation_key == "GET /health"


def test_sequence_plan_unknown_endpoint_raises(sample_spec):
    """Querying an unknown endpoint should raise ValueError."""
    graph = APIDependencyGraph(sample_spec)
    with pytest.raises(ValueError) as exc:
        graph.build_sequence_plan("DELETE /unknown_endpoint")
    assert "not found in dependency graph" in str(exc.value)
