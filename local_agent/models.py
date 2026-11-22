"""Core data models for Local Repository Testing Agent."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class LanguageType(str, Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    UNKNOWN = "unknown"


class FindingStatus(str, Enum):
    VERIFIED_FAILURE = "VERIFIED_FAILURE"
    LEAD = "LEAD"
    SETUP_GAP = "SETUP_GAP"
    PASSED_EXPECTED = "PASSED_EXPECTED"


class ParameterInfo(BaseModel):
    name: str
    type_annotation: Optional[str] = None
    default_value: Optional[str] = None
    has_default: bool = False


class ContractInfo(BaseModel):
    kind: str  # "raises", "requires", "returns", "invariant"
    target: str
    condition: str
    raw_text: str


class CodeSymbol(BaseModel):
    name: str
    file_path: str  # relative to repo root
    line_number: int
    kind: str  # "function", "class", "method"
    language: str
    parent_class: Optional[str] = None
    parameters: List[ParameterInfo] = Field(default_factory=list)
    return_type: Optional[str] = None
    docstring: Optional[str] = None
    contracts: List[ContractInfo] = Field(default_factory=list)
    risk_flags: List[str] = Field(default_factory=list)
    exported: bool = True


class ProjectInventory(BaseModel):
    repo_path: str
    languages: List[str] = Field(default_factory=list)
    manifests: List[str] = Field(default_factory=list)
    source_files: List[str] = Field(default_factory=list)
    test_files: List[str] = Field(default_factory=list)
    test_frameworks: List[str] = Field(default_factory=list)
    symbols: List[CodeSymbol] = Field(default_factory=list)
    setup_notes: List[str] = Field(default_factory=list)


class TestCandidate(BaseModel):
    id: str
    category: str  # "boundary_value", "malformed_input", "state_transition", "contract_violation", "ast_heuristic"
    symbol_name: str
    file_path: str
    language: str
    description: str
    inputs: Dict[str, Any] = Field(default_factory=dict)
    expected_behavior: str
    rationale: str
    is_stateful: bool = False
    state_sequence: List[Dict[str, Any]] = Field(default_factory=list)


class ExecutionResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    passed: bool
    error_message: Optional[str] = None
    failure_type: Optional[str] = None  # e.g., "ZeroDivisionError", "TypeError", "AssertionError"


class Finding(BaseModel):
    id: str
    status: FindingStatus
    category: str
    symbol_name: str
    file_path: str
    line_number: int
    language: str
    input_summary: str
    expected_behavior: str
    observed_behavior: str
    source_reference: str
    execution_evidence: str
    test_file_path: Optional[str] = None
    replay_command: Optional[str] = None
    reason_unconfirmed: Optional[str] = None
    run1_result: Optional[ExecutionResult] = None
    run2_replay_result: Optional[ExecutionResult] = None


class ScanReport(BaseModel):
    repo_path: str
    scan_timestamp: str
    scan_duration_seconds: float
    languages: List[str]
    files_scanned: int
    symbols_analyzed: int
    candidates_generated: int
    tests_executed: int
    verified_failures_count: int
    leads_count: int
    setup_gaps_count: int
    source_integrity_verified: bool
    verified_failures: List[Finding] = Field(default_factory=list)
    leads: List[Finding] = Field(default_factory=list)
    setup_gaps: List[Finding] = Field(default_factory=list)
    untested_areas: List[str] = Field(default_factory=list)

