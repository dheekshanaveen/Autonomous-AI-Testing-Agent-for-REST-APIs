"""API Endpoint Dependency Graph for Autonomous AI Testing Agent.

Identifies, models, and orders dependencies between API operations using NetworkX.
Enables multi-step test sequences (e.g. Login -> Create Order -> Retrieve Order)
by propagating tokens, IDs, and parameters across requests.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
import networkx as nx
from pydantic import BaseModel, Field

from agent.spec_reader import APISpecification, OperationDefinition

logger = logging.getLogger("agent.dependency_graph")


class DependencyRelation(BaseModel):
    """Describes a single data dependency from a producer operation to a consumer operation."""

    producer_key: str = Field(..., description="Producer operation key (e.g. 'POST /auth/login')")
    consumer_key: str = Field(..., description="Consumer operation key (e.g. 'POST /orders')")
    source_location: str = Field(..., description="Source location: 'body', 'header', or 'status'")
    source_field: str = Field(..., description="Field name in producer's response (e.g. 'access_token', 'id')")
    target_location: str = Field(..., description="Target location: 'auth_token', 'path_params', 'query_params', 'body'")
    target_field: str = Field(..., description="Field name in consumer's request (e.g. 'order_id', 'auth_token')")
    description: str = Field(default="", description="Human-readable explanation of the dependency")


class SequenceStep(BaseModel):
    """A single step in an executable test sequence."""

    step_index: int
    operation: OperationDefinition
    operation_key: str
    dependencies: List[DependencyRelation] = Field(default_factory=list)


class SequencePlan(BaseModel):
    """An ordered execution plan of dependent API operations."""

    name: str
    target_operation_key: str
    steps: List[SequenceStep] = Field(default_factory=list)

    @property
    def operation_keys(self) -> List[str]:
        return [step.operation_key for step in self.steps]


class APIDependencyGraph:
    """Directed graph representing producer-consumer relationships across API endpoints."""

    def __init__(self, spec: Optional[APISpecification] = None):
        self.spec: Optional[APISpecification] = spec
        self.graph: nx.DiGraph = nx.DiGraph()
        self._relations: List[DependencyRelation] = []

        if spec:
            self.build_graph(spec)

    @staticmethod
    def get_op_key(op: OperationDefinition) -> str:
        """Standardized operation identifier string."""
        return f"{op.method.upper()} {op.path}"

    def build_graph(self, spec: APISpecification) -> None:
        """Construct the NetworkX directed graph from the OpenAPI specification."""
        self.spec = spec
        self.graph.clear()
        self._relations.clear()

        # Add all operations as nodes in the graph
        for op in spec.operations:
            key = self.get_op_key(op)
            self.graph.add_node(key, operation=op)

        # 1. Discover explicit dependencies from OpenAPI response links
        self._discover_explicit_links(spec)

        # 2. Discover standard authentication dependencies
        self._discover_auth_dependencies(spec)

        # 3. Discover resource CRUD/Path-parameter dependencies
        self._discover_path_parameter_dependencies(spec)

    def add_dependency(self, relation: DependencyRelation) -> None:
        """Manually or programmatically register a dependency edge."""
        self._relations.append(relation)
        if not self.graph.has_edge(relation.producer_key, relation.consumer_key):
            self.graph.add_edge(
                relation.producer_key,
                relation.consumer_key,
                relations=[relation],
            )
        else:
            self.graph[relation.producer_key][relation.consumer_key]["relations"].append(relation)

    # --------------------------------------------------------------------------
    # Discovery Strategies
    # --------------------------------------------------------------------------

    def _discover_explicit_links(self, spec: APISpecification) -> None:
        """Extract explicit dependencies declared in OpenAPI operation links."""
        for op in spec.operations:
            producer_key = self.get_op_key(op)
            for link_name, link_data in op.links.items():
                target_op_id = link_data.get("operationId")
                params = link_data.get("parameters", {})

                # Find consumer operation by operationId
                consumer_op = next(
                    (o for o in spec.operations if o.operation_id == target_op_id),
                    None,
                )
                if not consumer_op:
                    continue

                consumer_key = self.get_op_key(consumer_op)
                for param_name, expr in params.items():
                    # Parse expression like $response.body#/id
                    match = re.search(r"\$response\.body#/(.+)", str(expr))
                    source_field = match.group(1) if match else "id"

                    relation = DependencyRelation(
                        producer_key=producer_key,
                        consumer_key=consumer_key,
                        source_location="body",
                        source_field=source_field,
                        target_location="path_params",
                        target_field=param_name,
                        description=f"OpenAPI Link '{link_name}' maps response body '{source_field}' to '{param_name}'",
                    )
                    self.add_dependency(relation)

    def _discover_auth_dependencies(self, spec: APISpecification) -> None:
        """Identify login operations and link them to operations requiring security."""
        # Find login/auth operation (POST /auth/login or operation with 'login' in path/id)
        login_op = next(
            (
                op for op in spec.operations
                if op.method == "POST" and ("login" in op.path.lower() or "auth" in op.path.lower())
            ),
            None,
        )
        if not login_op:
            return

        login_key = self.get_op_key(login_op)

        # Every operation that requires security depends on this login operation
        for op in spec.operations:
            if op.security and self.get_op_key(op) != login_key:
                consumer_key = self.get_op_key(op)
                relation = DependencyRelation(
                    producer_key=login_key,
                    consumer_key=consumer_key,
                    source_location="body",
                    source_field="access_token",
                    target_location="auth_token",
                    target_field="auth_token",
                    description="Authentication token from login required by secured endpoint",
                )
                self.add_dependency(relation)

    def _discover_path_parameter_dependencies(self, spec: APISpecification) -> None:
        """Match resource collection creation (e.g. POST /orders) to item endpoints (e.g. GET /orders/{order_id})."""
        for consumer_op in spec.operations:
            consumer_key = self.get_op_key(consumer_op)

            # Check if consumer requires path parameters like {order_id} or {id}
            path_params = [p for p in consumer_op.parameters if p.location == "path"]
            if not path_params:
                continue

            for param in path_params:
                # E.g., for /orders/{order_id}, base path is /orders, param is order_id
                base_path = re.sub(r"/\{[^/]+\}", "", consumer_op.path)

                # Find a POST endpoint matching base_path (the resource creator)
                producer_op = next(
                    (
                        o for o in spec.operations
                        if o.method == "POST" and o.path.rstrip("/") == base_path.rstrip("/")
                    ),
                    None,
                )

                if producer_op and self.get_op_key(producer_op) != consumer_key:
                    producer_key = self.get_op_key(producer_op)
                    relation = DependencyRelation(
                        producer_key=producer_key,
                        consumer_key=consumer_key,
                        source_location="body",
                        source_field="id",
                        target_location="path_params",
                        target_field=param.name,
                        description=(
                            f"Resource creation '{producer_key}' returns ID used by "
                            f"'{consumer_key}' parameter '{param.name}'"
                        ),
                    )
                    self.add_dependency(relation)

    # --------------------------------------------------------------------------
    # Sequence Planning
    # --------------------------------------------------------------------------

    def get_dependencies_for(self, operation_key: str) -> List[DependencyRelation]:
        """Return all inbound dependency relations for a specific operation."""
        return [r for r in self._relations if r.consumer_key == operation_key]

    def build_sequence_plan(self, target_operation_key: str) -> SequencePlan:
        """Generate an ordered execution sequence plan leading up to the target operation.

        Uses NetworkX ancestor subgraph and topological sort so all prerequisites
        execute in the required order.
        """
        if target_operation_key not in self.graph:
            raise ValueError(f"Operation '{target_operation_key}' not found in dependency graph.")

        # Find all prerequisites (ancestors in directed graph)
        ancestors = nx.ancestors(self.graph, target_operation_key)
        relevant_nodes = ancestors.union({target_operation_key})

        # Subgraph of relevant nodes
        subgraph = self.graph.subgraph(relevant_nodes)

        # Order operations topologically (prerequisites first)
        ordered_keys: List[str]
        try:
            ordered_keys = list(nx.topological_sort(subgraph))
        except nx.NetworkXUnfeasible:
            # Fallback if cycles exist
            ordered_keys = list(relevant_nodes)

        steps: List[SequenceStep] = []
        for index, op_key in enumerate(ordered_keys):
            op_def = self.graph.nodes[op_key]["operation"]
            step_deps = self.get_dependencies_for(op_key)
            steps.append(
                SequenceStep(
                    step_index=index + 1,
                    operation=op_def,
                    operation_key=op_key,
                    dependencies=step_deps,
                )
            )

        return SequencePlan(
            name=f"Sequence for {target_operation_key}",
            target_operation_key=target_operation_key,
            steps=steps,
        )
