"""Test Minimizer for Autonomous AI Testing Agent for REST APIs.

Implements delta-debugging minimization to reduce failing multi-step request
sequences and payload fields to their smallest practical reproducing subset
while preserving the exact same underlying bug and user identities.
"""

from __future__ import annotations

import json
import logging
import uuid
from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from agent.executor import ExecutionResult, RequestExecutor
from agent.oracles import BugFinding, BOLAOracle

logger = logging.getLogger("agent.minimizer")


# ------------------------------------------------------------------------------
# Structured Test Sequence Models
# ------------------------------------------------------------------------------

class TestSequenceStep(BaseModel):
    """A single executable step within an ordered test sequence."""

    __test__ = False  # Prevent pytest from collecting this class as a test suite

    step_id: str = Field(default_factory=lambda: f"step-{uuid.uuid4().hex[:6]}")
    name: str = Field(..., description="Descriptive name of the step")
    method: str = Field(..., description="HTTP Method (GET, POST, etc.)")
    path: str = Field(..., description="Target path or template, e.g. '/orders/{order_id}'")
    path_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters substituted into path (may contain '${var}' context references)",
    )
    query_params: Dict[str, Any] = Field(default_factory=dict)
    headers: Dict[str, str] = Field(default_factory=dict)
    json_body: Optional[Any] = Field(default=None, description="Request payload")
    auth_token_var: Optional[str] = Field(
        default=None,
        description="Name of context variable storing Bearer token",
    )
    capture_vars: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of response body fields to context variable names",
    )
    is_essential_target: bool = Field(
        default=False,
        description="True if this step is the probe that triggers the vulnerability",
    )

    def summary(self) -> str:
        return f"{self.method} {self.path} ({self.name})"


class SequenceExecutionResult(BaseModel):
    """Result of running a complete TestSequence."""

    __test__ = False

    steps: List[TestSequenceStep] = Field(default_factory=list)
    execution_results: List[ExecutionResult] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)
    all_success: bool = Field(default=True)


class TestSequence(BaseModel):
    """An ordered series of dependent HTTP request steps."""

    __test__ = False

    name: str = Field(default="Test Sequence")
    steps: List[TestSequenceStep] = Field(default_factory=list)
    description: str = Field(default="")

    @property
    def request_count(self) -> int:
        return len(self.steps)

    def clone(self) -> TestSequence:
        """Deep copy the test sequence."""
        return deepcopy(self)

    def signature(self) -> str:
        """Deterministic fingerprint of steps and payloads for caching."""
        tokens = []
        for s in self.steps:
            body_str = json.dumps(s.json_body, sort_keys=True) if s.json_body is not None else ""
            tokens.append(f"{s.method}:{s.path}:{s.auth_token_var}:{body_str}")
        return "|".join(tokens)

    def execute(
        self,
        executor: RequestExecutor,
        reset_state: bool = True,
    ) -> SequenceExecutionResult:
        """Execute all steps in order, passing dynamic outputs through context."""
        if reset_state:
            executor.post("/admin/reset")

        context: Dict[str, Any] = {}
        traces: List[ExecutionResult] = []
        all_success = True

        for step in self.steps:
            # 1. Resolve path parameter variables from context
            resolved_path_params = {}
            for k, v in step.path_params.items():
                if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
                    var_name = v[2:-1]
                    resolved_path_params[k] = context.get(var_name, v)
                else:
                    resolved_path_params[k] = v

            # 2. Resolve authentication token from context
            auth_token = None
            if step.auth_token_var:
                auth_token = context.get(step.auth_token_var)

            # 3. Resolve json body variables
            resolved_body = deepcopy(step.json_body)
            if isinstance(resolved_body, dict):
                for bk, bv in list(resolved_body.items()):
                    if isinstance(bv, str) and bv.startswith("${") and bv.endswith("}"):
                        resolved_body[bk] = context.get(bv[2:-1], bv)

            # 4. Execute HTTP request
            res = executor.execute(
                method=step.method,
                path=step.path,
                path_params=resolved_path_params,
                query_params=step.query_params,
                headers=step.headers,
                json_body=resolved_body,
                auth_token=auth_token,
            )
            traces.append(res)

            # Stop early if a non-target prerequisite request failed
            if not res.is_success and not step.is_essential_target:
                all_success = False
                break

            # 5. Capture response fields into context for downstream steps
            if res.response and res.response.is_json and isinstance(res.response.body, dict):
                for src_field, target_var in step.capture_vars.items():
                    if src_field in res.response.body:
                        context[target_var] = res.response.body[src_field]

        return SequenceExecutionResult(
            steps=self.steps,
            execution_results=traces,
            context=context,
            all_success=all_success,
        )

    @classmethod
    def from_bola_scenario(cls, with_noise: bool = True) -> TestSequence:
        """Create a BOLA test sequence, optionally containing redundant noise requests.

        When with_noise=True, adds 6 unnecessary /health checks and redundant body fields,
        resulting in 10 requests total. The minimal necessary sequence has exactly 4 requests.
        """
        steps: List[TestSequenceStep] = []

        if with_noise:
            steps.append(
                TestSequenceStep(
                    name="Pre-Check System Health 1",
                    method="GET",
                    path="/health",
                )
            )

        # 1. Login Alice (Essential Prerequisite 1)
        steps.append(
            TestSequenceStep(
                name="Login Alice",
                method="POST",
                path="/auth/login",
                json_body={"username": "alice", "password": "alice123"},
                capture_vars={"access_token": "alice_token", "user_id": "alice_id"},
            )
        )

        if with_noise:
            steps.append(
                TestSequenceStep(
                    name="Intermittent Health Ping 2",
                    method="GET",
                    path="/health",
                )
            )

        # 2. Create Order as Alice (Essential Prerequisite 2)
        order_payload: Dict[str, Any] = {
            "item_name": "Autonomous Drone",
            "quantity": 1,
            "total_price": 299.99,
        }
        if with_noise:
            # Add redundant fields to payload for body minimization
            order_payload["notes"] = "Please handle with care"
            order_payload["gift_wrap"] = True

        steps.append(
            TestSequenceStep(
                name="Create Alice Order",
                method="POST",
                path="/orders",
                auth_token_var="alice_token",
                json_body=order_payload,
                capture_vars={"id": "order_id"},
            )
        )

        if with_noise:
            steps.append(
                TestSequenceStep(
                    name="Intermittent Health Ping 3",
                    method="GET",
                    path="/health",
                )
            )

        # 3. Login Bob (Essential Prerequisite 3)
        steps.append(
            TestSequenceStep(
                name="Login Bob",
                method="POST",
                path="/auth/login",
                json_body={"username": "bob", "password": "bob123"},
                capture_vars={"access_token": "bob_token", "user_id": "bob_id"},
            )
        )

        if with_noise:
            steps.append(
                TestSequenceStep(
                    name="Intermittent Health Ping 4",
                    method="GET",
                    path="/health",
                )
            )

        # 4. Bob Accesses Alice's Order (Essential Target Probe)
        steps.append(
            TestSequenceStep(
                name="Bob Accesses Alice Order (BOLA Probe)",
                method="GET",
                path="/orders/{order_id}",
                path_params={"order_id": "${order_id}"},
                auth_token_var="bob_token",
                is_essential_target=True,
            )
        )

        if with_noise:
            steps.append(
                TestSequenceStep(
                    name="Post-Check System Health 5",
                    method="GET",
                    path="/health",
                )
            )
            steps.append(
                TestSequenceStep(
                    name="Post-Check System Health 6",
                    method="GET",
                    path="/health",
                )
            )

        desc = (
            "10-request noisy BOLA sequence with redundant health checks"
            if with_noise
            else "4-request minimal BOLA reproduction sequence"
        )
        return cls(name="BOLA Cross-User Reproduction Sequence", steps=steps, description=desc)


# ------------------------------------------------------------------------------
# Minimization Result Model
# ------------------------------------------------------------------------------

class MinimizationResult(BaseModel):
    """Summary of a delta-debugging test reduction."""

    __test__ = False

    minimization_id: str = Field(default_factory=lambda: f"min-{uuid.uuid4().hex[:8]}")
    target_bug_type: str = Field(..., description="Bug classification preserved during minimization")
    original_request_count: int = Field(..., description="Number of requests before minimization")
    minimized_request_count: int = Field(..., description="Number of requests after minimization")
    reduction_ratio: float = Field(
        ...,
        description="Reduction ratio: 1 - (minimized_count / original_count)",
    )
    reduction_percentage: float = Field(..., description="Percentage reduced: ratio * 100")
    is_reduced: bool = Field(default=False, description="True if at least one request was removed")
    removed_step_names: List[str] = Field(
        default_factory=list,
        description="Names of unnecessary requests pruned from sequence",
    )
    removed_payload_fields: List[str] = Field(
        default_factory=list,
        description="Payload fields safely pruned from requests",
    )
    evaluations_performed: int = Field(default=0, description="Total candidate sequences evaluated")
    original_sequence: TestSequence
    minimized_sequence: TestSequence

    def summary(self) -> str:
        """One-line summary of minimization outcome."""
        if self.is_reduced:
            return (
                f"[REDUCED] {self.original_request_count} -> {self.minimized_request_count} requests "
                f"({self.reduction_percentage:.1f}% reduction). Bug: '{self.target_bug_type}' preserved."
            )
        return (
            f"[UNCHANGED] {self.original_request_count} requests (0.0% reduction). "
            f"Test was already minimal."
        )

    def format_report(self) -> str:
        """Multi-line ASCII formatted report card."""
        status_tag = "TEST MINIMIZED" if self.is_reduced else "ALREADY MINIMAL"
        lines = [
            "=" * 76,
            f"TEST MINIMIZATION REPORT: {self.minimization_id} [{status_tag}]",
            "=" * 76,
            f"Target Bug:           {self.target_bug_type}",
            f"Original Requests:    {self.original_request_count}",
            f"Minimized Requests:   {self.minimized_request_count}",
            f"Reduction Ratio:      {self.reduction_ratio:.4f} ({self.reduction_percentage:.1f}%)",
            f"Evaluations Tested:   {self.evaluations_performed}",
            "-" * 76,
            "PRUNED REQUESTS:",
        ]
        if self.removed_step_names:
            for s in self.removed_step_names:
                lines.append(f"  [-] {s}")
        else:
            lines.append("  (None removed - all requests were essential)")

        lines.append("-" * 76)
        lines.append("PRUNED PAYLOAD FIELDS:")
        if self.removed_payload_fields:
            for f in self.removed_payload_fields:
                lines.append(f"  [-] {f}")
        else:
            lines.append("  (None removed)")

        lines.append("-" * 76)
        lines.append("MINIMIZED REQUEST SEQUENCE:")
        for idx, step in enumerate(self.minimized_sequence.steps, 1):
            body_preview = f" Body: {json.dumps(step.json_body)}" if step.json_body else ""
            lines.append(f"  {idx}. {step.method} {step.path} [{step.name}]{body_preview}")

        lines.append("=" * 76)
        return "\n".join(lines)


# ------------------------------------------------------------------------------
# Test Minimizer Implementation
# ------------------------------------------------------------------------------

class TestMinimizer:
    """Reduces failing test sequences to their smallest practical reproduction."""

    __test__ = False

    def __init__(self, executor: Optional[RequestExecutor] = None):
        self.executor = executor or RequestExecutor(base_url="http://127.0.0.1:8000")

    def minimize_sequence(
        self,
        sequence: TestSequence,
        evaluator_fn: Callable[[TestSequence], Tuple[bool, Optional[BugFinding]]],
        target_bug_type: str = "BOLA_VIOLATION",
    ) -> MinimizationResult:
        """Run delta-debugging sequence and field reduction.

        Args:
            sequence: The starting failing/vulnerable test sequence.
            evaluator_fn: Callable accepting a candidate TestSequence, resetting state,
                          and returning (is_reproduced: bool, finding: Optional[BugFinding]).
            target_bug_type: Classification string of the target bug to preserve.

        Returns:
            MinimizationResult with metrics and minimized TestSequence.
        """
        original_count = sequence.request_count
        visited_cache: Dict[str, bool] = {}
        evaluations_count = 0

        # Step 1: Verify starting sequence actually reproduces the target defect
        sig = sequence.signature()
        initial_ok, initial_finding = evaluator_fn(sequence)
        visited_cache[sig] = initial_ok
        evaluations_count += 1

        if not initial_ok:
            logger.warning("Starting sequence did not reproduce '%s'. Minimization aborted.", target_bug_type)
            return MinimizationResult(
                target_bug_type=target_bug_type,
                original_request_count=original_count,
                minimized_request_count=original_count,
                reduction_ratio=0.0,
                reduction_percentage=0.0,
                is_reduced=False,
                evaluations_performed=evaluations_count,
                original_sequence=sequence,
                minimized_sequence=sequence,
            )

        current_steps: List[TestSequenceStep] = deepcopy(sequence.steps)
        removed_steps: List[str] = []
        removed_fields: List[str] = []

        # Step 2: Request-level Delta Debugging (1-minimal deletion pass)
        changed = True
        while changed:
            changed = False
            for i in range(len(current_steps)):
                # Do not delete the essential target probe if it is the final step
                if current_steps[i].is_essential_target and i == len(current_steps) - 1:
                    continue

                # Candidate sequence omitting step i
                candidate_steps = [s for j, s in enumerate(current_steps) if j != i]
                candidate_seq = TestSequence(name=sequence.name, steps=candidate_steps)
                cand_sig = candidate_seq.signature()

                if cand_sig in visited_cache:
                    reproduced = visited_cache[cand_sig]
                else:
                    reproduced, finding = evaluator_fn(candidate_seq)
                    visited_cache[cand_sig] = reproduced
                    evaluations_count += 1

                if reproduced:
                    removed_steps.append(current_steps[i].name)
                    logger.info("Successfully pruned request step: %s", current_steps[i].name)
                    current_steps = candidate_steps
                    changed = True
                    break  # Restart pass with shorter sequence

        # Step 3: Payload field minimization for remaining steps
        for step_idx, step in enumerate(current_steps):
            if isinstance(step.json_body, dict):
                body_keys = list(step.json_body.keys())
                for key in body_keys:
                    candidate_body = {k: v for k, v in step.json_body.items() if k != key}
                    candidate_steps = deepcopy(current_steps)
                    candidate_steps[step_idx].json_body = candidate_body
                    candidate_seq = TestSequence(name=sequence.name, steps=candidate_steps)
                    cand_sig = candidate_seq.signature()

                    if cand_sig in visited_cache:
                        reproduced = visited_cache[cand_sig]
                    else:
                        reproduced, _ = evaluator_fn(candidate_seq)
                        visited_cache[cand_sig] = reproduced
                        evaluations_count += 1

                    if reproduced:
                        removed_fields.append(f"{step.name}.{key}")
                        logger.info("Successfully pruned body field '%s' from %s", key, step.name)
                        current_steps[step_idx].json_body = candidate_body

        minimized_count = len(current_steps)
        reduction_ratio = 1.0 - (minimized_count / original_count) if original_count > 0 else 0.0
        reduction_percentage = reduction_ratio * 100.0
        is_reduced = minimized_count < original_count or len(removed_fields) > 0

        minimized_seq = TestSequence(
            name=f"{sequence.name} (Minimized)",
            steps=current_steps,
            description=f"Minimized version of {sequence.name}",
        )

        return MinimizationResult(
            target_bug_type=target_bug_type,
            original_request_count=original_count,
            minimized_request_count=minimized_count,
            reduction_ratio=reduction_ratio,
            reduction_percentage=reduction_percentage,
            is_reduced=is_reduced,
            removed_step_names=removed_steps,
            removed_payload_fields=removed_fields,
            evaluations_performed=evaluations_count,
            original_sequence=sequence,
            minimized_sequence=minimized_seq,
        )

    def minimize_bola_scenario(
        self,
        starting_sequence: Optional[TestSequence] = None,
    ) -> MinimizationResult:
        """Run BOLA sequence minimization against the target API."""
        seq = starting_sequence or TestSequence.from_bola_scenario(with_noise=True)
        oracle = BOLAOracle()

        def bola_evaluator(cand: TestSequence) -> Tuple[bool, Optional[BugFinding]]:
            res = cand.execute(executor=self.executor, reset_state=True)
            if not res.execution_results:
                return False, None

            # Locate the probe step execution result
            probe_exec = None
            for s, r in zip(cand.steps, res.execution_results):
                if s.is_essential_target or "/orders/{order_id}" in s.path:
                    probe_exec = r
                    break

            if not probe_exec:
                return False, None

            alice_id = res.context.get("alice_id", "user-alice")
            bob_id = res.context.get("bob_id", "user-bob")
            order_id = res.context.get("order_id")

            if not order_id:
                return False, None

            finding = oracle.check_access(
                execution_result=probe_exec,
                resource_owner_id=alice_id,
                accessor_user_id=bob_id,
                resource_id=order_id,
                endpoint_template="/orders/{order_id}",
            )

            if finding is not None and finding.bug_type == "BOLA_VIOLATION" and finding.is_confirmed:
                return True, finding
            return False, None

        return self.minimize_sequence(
            sequence=seq,
            evaluator_fn=bola_evaluator,
            target_bug_type="BOLA_VIOLATION",
        )


if __name__ == "__main__":
    import sys

    target_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    print(f"[*] Running Test Minimizer against: {target_url}")

    cli_executor = RequestExecutor(base_url=target_url)
    minimizer = TestMinimizer(executor=cli_executor)

    print("[*] Starting delta-debugging minimization on noisy 10-request BOLA test sequence...")
    noisy_seq = TestSequence.from_bola_scenario(with_noise=True)
    result = minimizer.minimize_bola_scenario(starting_sequence=noisy_seq)

    print("\n" + result.format_report() + "\n")
