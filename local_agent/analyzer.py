"""Analyzer module: derives boundary cases, malformed inputs, contracts, and state transitions."""

import uuid
from typing import Any, Dict, List, Optional
from local_agent.models import CodeSymbol, ProjectInventory, TestCandidate


class TestCandidateAnalyzer:
    """Analyzes project symbols and extracts targeted test candidates."""

    @classmethod
    def analyze(cls, inventory: ProjectInventory) -> List[TestCandidate]:
        candidates: List[TestCandidate] = []
        for symbol in inventory.symbols:
            # We focus on functions and classes (methods are tested via class stateful tests)
            if symbol.kind == "function" and not symbol.name.startswith("__"):
                candidates.extend(cls._analyze_function_candidates(symbol))
            elif symbol.kind == "class":
                candidates.extend(cls._analyze_class_candidates(symbol, inventory))

        return candidates

    @classmethod
    def _analyze_function_candidates(cls, symbol: CodeSymbol) -> List[TestCandidate]:
        candidates: List[TestCandidate] = []
        params = symbol.parameters

        if not params:
            # Zero-arg function: call it directly
            candidates.append(
                TestCandidate(
                    id=f"cand-{uuid.uuid4().hex[:8]}",
                    category="boundary_value",
                    symbol_name=symbol.name,
                    file_path=symbol.file_path,
                    language=symbol.language,
                    description=f"Zero-argument invocation of {symbol.name}",
                    inputs={},
                    expected_behavior=f"Should execute {symbol.name} without crashing",
                    rationale="Baseline execution of no-argument callable.",
                )
            )
            return candidates

        # 1. AST Heuristics
        for risk in symbol.risk_flags:
            if risk == "zero_division":
                # Find the divisor param or first numeric param
                inputs: Dict[str, Any] = {}
                for p in params:
                    ann = (p.type_annotation or "").lower()
                    p_name_lower = p.name.lower()
                    if "list" in ann or any(k in p_name_lower for k in ["seq", "values", "items", "records"]):
                        inputs[p.name] = [1.0, 2.0, 3.0]
                    elif "str" in ann:
                        inputs[p.name] = "test"
                    elif "dict" in ann:
                        inputs[p.name] = {"key": 1}
                    elif any(k in p_name_lower for k in ["divisor", "scale", "denom", "window", "b", "step", "n", "size", "limit"]):
                        inputs[p.name] = 0
                    elif "int" in ann or "float" in ann:
                        inputs[p.name] = 0
                    else:
                        inputs[p.name] = cls._safe_default_value(p)
                candidates.append(
                    TestCandidate(
                        id=f"cand-{uuid.uuid4().hex[:8]}",
                        category="ast_heuristic",
                        symbol_name=symbol.name,
                        file_path=symbol.file_path,
                        language=symbol.language,
                        description=f"Zero divisor test for {symbol.name}",
                        inputs=inputs,
                        expected_behavior="Should handle zero divisor safely without uncaught ZeroDivisionError",
                        rationale="AST inspection detected division/modulo by parameter without zero guard.",
                    )
                )

            elif risk in {"empty_sequence", "empty_collection"}:
                inputs = {}
                for p in params:
                    ann = (p.type_annotation or "").lower()
                    p_name_lower = p.name.lower()
                    if "list" in ann or any(k in p_name_lower for k in ["list", "seq", "items", "records", "arr"]):
                        inputs[p.name] = []
                    else:
                        inputs[p.name] = cls._safe_default_value(p)
                candidates.append(
                    TestCandidate(
                        id=f"cand-{uuid.uuid4().hex[:8]}",
                        category="boundary_value",
                        symbol_name=symbol.name,
                        file_path=symbol.file_path,
                        language=symbol.language,
                        description=f"Empty sequence input for {symbol.name}",
                        inputs=inputs,
                        expected_behavior="Should handle empty sequence safely without IndexError or undefined crash",
                        rationale="AST inspection detected indexing or pop without empty collection guard.",
                    )
                )

            elif risk in {"none_dereference", "js_null_undefined"}:
                inputs = {}
                for p in params:
                    inputs[p.name] = None
                candidates.append(
                    TestCandidate(
                        id=f"cand-{uuid.uuid4().hex[:8]}",
                        category="malformed_input",
                        symbol_name=symbol.name,
                        file_path=symbol.file_path,
                        language=symbol.language,
                        description=f"Null/None dereference test for {symbol.name}",
                        inputs=inputs,
                        expected_behavior="Should validate against null/None without uncaught AttributeError/TypeError",
                        rationale="AST inspection detected attribute or member access on unvalidated parameter.",
                    )
                )

        # 2. Documented Contracts
        for contract in symbol.contracts:
            if contract.kind == "raises":
                inputs = {}
                for p in params:
                    p_name_lower = p.name.lower()
                    is_target = (p_name_lower in contract.condition.lower()) or (
                        p_name_lower in {"denominator", "denom", "window_size", "x", "n", "divisor", "scale"}
                    )
                    if is_target:
                        if "neg" in contract.condition.lower() or "<" in contract.condition:
                            inputs[p.name] = -1
                        elif "zero" in contract.condition.lower() or "=" in contract.condition:
                            inputs[p.name] = 0
                        elif "empty" in contract.condition.lower():
                            inputs[p.name] = "" if "str" in (p.type_annotation or "").lower() else []
                        else:
                            inputs[p.name] = -1
                    else:
                        inputs[p.name] = cls._safe_default_value(p)
                candidates.append(
                    TestCandidate(
                        id=f"cand-{uuid.uuid4().hex[:8]}",
                        category="contract_violation",
                        symbol_name=symbol.name,
                        file_path=symbol.file_path,
                        language=symbol.language,
                        description=f"Contract check ({contract.raw_text}) for {symbol.name}",
                        inputs=inputs,
                        expected_behavior=f"Should raise {contract.target} as documented: {contract.raw_text}",
                        rationale=f"Docstring explicitly specifies: {contract.raw_text}",
                    )
                )

        # 3. Standard Boundary Values
        boundary_sets = [
            ("all_zeros", {p.name: cls._boundary_val(p, "zero") for p in params}),
            ("negative_values", {p.name: cls._boundary_val(p, "negative") for p in params}),
            ("empty_containers", {p.name: cls._boundary_val(p, "empty") for p in params}),
        ]
        for name_suffix, inp in boundary_sets:
            candidates.append(
                TestCandidate(
                    id=f"cand-{uuid.uuid4().hex[:8]}",
                    category="boundary_value",
                    symbol_name=symbol.name,
                    file_path=symbol.file_path,
                    language=symbol.language,
                    description=f"Boundary inputs ({name_suffix}) for {symbol.name}",
                    inputs=inp,
                    expected_behavior="Should process or reject boundary input predictably without unhandled crash",
                    rationale=f"Boundary value testing on {name_suffix}.",
                )
            )

        # 4. Malformed Input (Type Mismatches)
        malformed_sets = [
            ("string_instead_of_int", {p.name: "invalid_string_input" for p in params}),
            ("none_payload", {p.name: None for p in params}),
        ]
        for name_suffix, inp in malformed_sets:
            candidates.append(
                TestCandidate(
                    id=f"cand-{uuid.uuid4().hex[:8]}",
                    category="malformed_input",
                    symbol_name=symbol.name,
                    file_path=symbol.file_path,
                    language=symbol.language,
                    description=f"Malformed input ({name_suffix}) for {symbol.name}",
                    inputs=inp,
                    expected_behavior="Should cleanly reject malformed input with validation error or graceful response",
                    rationale=f"Type mutation and malformed input testing ({name_suffix}).",
                )
            )

        return candidates


    @classmethod
    def _analyze_class_candidates(
        cls, class_symbol: CodeSymbol, inventory: ProjectInventory
    ) -> List[TestCandidate]:
        candidates: List[TestCandidate] = []
        # Find methods belonging to this class
        methods = [
            s for s in inventory.symbols
            if s.parent_class == class_symbol.name and s.file_path == class_symbol.file_path
        ]
        if not methods:
            return candidates

        method_names = [m.name for m in methods if not m.name.startswith("__")]

        # Look for queue/stack/session/stateful patterns:
        # e.g. pop, dequeue, get, finish, stop, close before push, enqueue, put, start, open
        consuming_names = [m for m in method_names if m in {"pop", "dequeue", "get", "pull", "finish", "stop", "close", "read"}]
        producing_names = [m for m in method_names if m in {"push", "enqueue", "put", "add", "start", "open", "write"}]

        if consuming_names:
            first_consumer = consuming_names[0]
            # State sequence: instantiate -> call consumer immediately on empty state
            candidates.append(
                TestCandidate(
                    id=f"cand-{uuid.uuid4().hex[:8]}",
                    category="state_transition",
                    symbol_name=class_symbol.name,
                    file_path=class_symbol.file_path,
                    language=class_symbol.language,
                    description=f"Premature state transition: call {first_consumer}() before setup in {class_symbol.name}",
                    inputs={},
                    expected_behavior=f"Should handle empty/uninitialized state in {first_consumer}() gracefully (raise expected exception or return None/sentinel)",
                    rationale=f"Stateful transition check: invocation of consumer method {first_consumer} on initial state.",
                    is_stateful=True,
                    state_sequence=[
                        {"action": "instantiate", "args": []},
                        {"action": "call", "method": first_consumer, "args": []},
                    ],
                )
            )

        if producing_names and consuming_names:
            producer = producing_names[0]
            consumer = consuming_names[0]
            # Sequence: add 1 item, consume 2 items (underflow check)
            candidates.append(
                TestCandidate(
                    id=f"cand-{uuid.uuid4().hex[:8]}",
                    category="state_transition",
                    symbol_name=class_symbol.name,
                    file_path=class_symbol.file_path,
                    language=class_symbol.language,
                    description=f"State underflow sequence on {class_symbol.name}: 1 {producer} followed by 2 {consumer} calls",
                    inputs={},
                    expected_behavior=f"Second call to {consumer}() should handle empty state cleanly without crashing",
                    rationale="State underflow testing on container/state machine.",
                    is_stateful=True,
                    state_sequence=[
                        {"action": "instantiate", "args": []},
                        {"action": "call", "method": producer, "args": [42]},
                        {"action": "call", "method": consumer, "args": []},
                        {"action": "call", "method": consumer, "args": []},
                    ],
                )
            )

        return candidates

    @classmethod
    def _boundary_val(cls, param, boundary_type: str) -> Any:
        ann = (param.type_annotation or "").lower()
        p_name = param.name.lower()
        if "list" in ann or any(k in p_name for k in ["values", "items", "records", "seq"]):
            if boundary_type == "empty":
                return []
            elif boundary_type == "negative":
                return [-1.0, -2.0]
            else:
                return [0.0, 0.0]
        if "str" in ann:
            return "" if boundary_type == "empty" else "test"
        if "dict" in ann:
            return {} if boundary_type == "empty" else {"key": 1}
        # Numeric
        if boundary_type == "negative":
            return -1
        elif boundary_type == "zero":
            return 0
        else:
            return 0

    @staticmethod
    def _safe_default_value(param) -> Any:
        ann = (param.type_annotation or "").lower()
        if "int" in ann:
            return 1
        if "float" in ann:
            return 1.0
        if "str" in ann:
            return "test"
        if "list" in ann:
            return [1]
        if "dict" in ann:
            return {"key": "val"}
        if "bool" in ann:
            return True
        return 1

    @staticmethod
    def _parse_default(default_val_str: Optional[str]) -> Any:
        if not default_val_str:
            return 0
        if default_val_str in {"0", "0.0", "''", '""', "None", "False"}:
            return 0
        return 1

