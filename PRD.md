# Product Requirements Document (PRD)

## Project: Autonomous AI Testing Agent for REST APIs

---

## 1. Executive Summary & Vision

The **Autonomous AI Testing Agent for REST APIs** is an AI-assisted, automated testing framework designed to discover functional bugs, specification non-conformance, and critical security vulnerabilities—specifically Broken Object Level Authorization (BOLA / IDOR)—in REST APIs without requiring manual test authoring.

Unlike standard fuzzers or black-box scanners that blindly spray endpoints with random payloads, this agent:
1. Systematically parses and interprets OpenAPI specifications (3.0.x and 3.1.x).
2. Maps producer-consumer relationships and execution dependencies between endpoints using directed graphs.
3. Automatically synthesizes both valid (positive) and mutated (negative) test cases.
4. Executes complex, stateful multi-step sequences (e.g., *Login -> Create Resource -> Inspect Resource*).
5. Detects behavioral anomalies, authorization violations, and specification discrepancies using deterministic oracles.
6. Replays and delta-minimizes failing test sequences to isolate root causes.
7. Generates reproducible test reports and runnable pytest test files.

---

## 2. Core Architectural Principles

- **No Blind Trust in LLMs:** AI reasoning is strictly used for diagnosis and hypothesis generation in later stages; all bug confirmations require deterministic HTTP execution and evidence.
- **Layered, Modular Design:** Keeps the controlled sample target API strictly isolated from testing agent logic.
- **Fail-Safe & Secure:** Protects secrets through strict redaction of tokens and passwords in traces and logs. Prevents agent crashes during network failures or timeouts.
- **Reproducibility:** Every discovered flaw must be replayable from a clean state.

---

## 3. System Architecture & Components

```text
┌────────────────────────────────────────────────────────────────────────┐
│                         AUTONOMOUS TESTING AGENT                       │
├───────────────────────────────┬────────────────────────────────────────┤
│ 1. Spec Reader                │ Reads OpenAPI 3.x, resolves $ref       │
│    (agent/spec_reader.py)     │ schemas, extracts security & links     │
├───────────────────────────────┼────────────────────────────────────────┤
│ 2. Dependency Graph           │ NetworkX directed graph; models auth   │
│    (agent/dependency_graph.py)│ & resource CRUD dependencies           │
├───────────────────────────────┼────────────────────────────────────────┤
│ 3. Test Generator & Runner    │ Normal tests, invalid-input mutations, │
│    (agent/test_generator.py)  │ sequence plans & Schemathesis baseline │
├───────────────────────────────┼────────────────────────────────────────┤
│ 4. Request Executor           │ HTTP client with template substitution,│
│    (agent/executor.py)        │ Bearer auth, redaction & tracing       │
├───────────────────────────────┴────────────────────────────────────────┤
│ 5. Security & Bug Oracles (Step 5) [Pending]                           │
├────────────────────────────────────────────────────────────────────────┤
│ 6. Verification & Minimization (Step 6) [Pending]                      │
├────────────────────────────────────────────────────────────────────────┤
│ 7. AI Diagnosis & Reporting (Step 7) [Pending]                         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP Requests
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   CONTROLLED SAMPLE TARGET API                         │
│                    (sample_api/ - FastAPI Target)                      │
│ • Endpoints: /health, /auth/login, /orders, /orders/{id}, /admin/reset │
│ • Demo Accounts: Alice (Customer A), Bob (Customer B)                  │
│ • Intentional Vulnerability: BOLA on GET /orders/{order_id}            │
│ • Deterministic State Reset: POST /admin/reset                         │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Roadmap & Current Implementation Status

| Stage | Feature / Objective | Module(s) | Status | Test Coverage |
| :--- | :--- | :--- | :--- | :--- |
| **Step 1** | Controlled Sample API with intentional BOLA bug | `sample_api/` | **Completed** | 9 tests passed |
| **Step 2** | OpenAPI 3.x Specification Reader & $ref Resolver | `agent/spec_reader.py` | **Completed** | 16 tests passed |
| **Step 3** | Safe Request Executor, Redaction & Tracing | `agent/executor.py` | **Completed** | 13 tests passed |
| **Step 4** | Automatic Test Generator, Dependency Graph & Sequences | `agent/dependency_graph.py`, `agent/test_generator.py` | **Completed** | 16 tests passed |
| **Step 5** | Bug Detection Oracles & BOLA Verification | `agent/oracles.py` | **Completed** | 14 tests passed |
| **Step 6** | Flakiness Check, Replay & Test Minimization | `agent/verifier.py`, `agent/minimizer.py` | **Completed** | 11 tests passed |
| **Step 7** | LLM Diagnosis, Targeted Checks & Markdown/JSON Reports | `agent/reporter.py` | **Completed** | 11 tests passed |
| **Step 8** | Benchmarking & Schemathesis Baseline Comparisons | `benchmarks/` | *Next Up* | Pending |

---

## 5. Detailed Component Specifications

### 5.1 Controlled Sample Target API (`sample_api/`)
- **FastAPI application** bound to `127.0.0.1:8000`.
- **Predefined demo accounts:** `alice` (`alice123`, ID: `user-alice`) and `bob` (`bob123`, ID: `user-bob`).
- **Interactive docs:** Swagger UI (`/docs`), OpenAPI 3.1 JSON (`/openapi.json`).
- **Intentional BOLA Flaw:** `GET /orders/{order_id}` authenticates the caller but omits ownership validation, allowing Bob to read Alice's private order.
- **Deterministic Reset:** `POST /admin/reset` clears in-memory state and tokens.

### 5.2 OpenAPI Specification Reader (`agent/spec_reader.py`)
- Reads from live URLs, local JSON files, or Python dictionaries.
- Recursively resolves internal JSON pointer `$ref` components and prevents circular reference crashes.
- Discovers operations, parameters (path, query, header, cookie), request body schemas, response schemas, and authentication schemes (`HTTPBearer`).
- Robust exception hierarchy: `SpecConnectionError`, `SpecNotFoundError`, `SpecParseError`, `SpecValidationError`, `SpecResolutionError`.

### 5.3 Request Executor (`agent/executor.py`)
- Sends HTTP requests (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`).
- Substitutes URL template path parameters (e.g. `/orders/{order_id}` -> `/orders/ord-1`) with URL encoding.
- Injects Bearer tokens automatically for demo users.
- Redacts secrets from headers (`Authorization`, `Cookie`) and request bodies (`password`, `token`, `secret`).
- Captures `ExecutionResult` with status codes, headers, parsed bodies, and execution duration in milliseconds.
- Gracefully captures network errors and timeouts without crashing the agent.

### 5.4 Dependency Graph (`agent/dependency_graph.py`)
- Uses NetworkX directed graphs (`DiGraph`).
- Discovers:
  - **Explicit links:** Parses OpenAPI response links (`links`).
  - **Auth dependencies:** Links secured endpoints to the login operation.
  - **CRUD path dependencies:** Links item endpoints (`GET /orders/{order_id}`) to collection creators (`POST /orders`).
- Computes topological execution plans (`SequencePlan`) for multi-step sequences.

### 5.5 Test Generator & Runner (`agent/test_generator.py`)
- **Normal Tests:** Generates valid inputs compliant with schemas and expects documented 2xx status codes.
- **Invalid-Input Tests:** Systematically mutates schemas (omits required fields, injects type mismatches, tests boundary violations, tests missing tokens) and expects 400, 401, or 422.
- **Sequence Runner:** Executes multi-step plans (`Login -> Create Order -> Get Order`), passing dynamic context (tokens, order IDs) across steps.
- **Schemathesis Baseline:** Integrates Schemathesis 4.x property-based testing tagged `[SCHEMATHESIS]` to benchmark against our agent's tests.

### 5.6 Bug Detection Oracles & BOLA Verification (`agent/oracles.py`)
- **BugFinding Data Model:** Captures problem type, severity (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`), endpoint, method, redacted request details, expected behavior, actual response, explanation, and evidence. Distinguishes between `is_confirmed=True` (verified defect) and `is_confirmed=False` (suspicious anomaly).
- **Check 1 - ServerErrorOracle:** Detects 5xx internal server errors (e.g., HTTP 500, 502, 503). Records request and response as suspicious problem for investigation without prematurely confirming.
- **Check 2 - SchemaConformanceOracle:** Validates response status codes and response body payloads against OpenAPI schemas using standard JSON Schema validation (`jsonschema`). Flags type mismatches (e.g. price as string) and missing required properties. If behavior is not documented, does not invent rules.
- **Check 3 - BOLAOracle (OWASP API1:2023):** Implements end-to-end cross-user authorization testing:
  1. Login as Alice (`POST /auth/login`) -> retrieve token and ID.
  2. Create private order as Alice (`POST /orders`) -> retrieve order ID.
  3. Login as Bob (`POST /auth/login`) -> retrieve token and ID.
  4. Bob attempts `GET /orders/{order_id}` with Bob's token.
  5. Evaluates object ownership rule: if Bob receives Alice's private order (HTTP 200), flags critical confirmed BOLA vulnerability.
  6. Control check: Alice accessing her own order is confirmed legitimate and not flagged.
- **Credential Redaction:** Guaranteed zero leakage of plaintext passwords or Bearer tokens in findings.

### 5.7 Bug Verification & Test Minimization (`agent/verifier.py`, `agent/minimizer.py`)
- **Bug Verifier (`agent/verifier.py`):**
  - Replays failing and suspicious test scenarios from a clean starting state at least twice (`repeat_count >= 2`).
  - Classifies outcomes into `CONFIRMED_REPRODUCIBLE` (100% reproduction), `FLAKY` (inconsistent reproduction across runs), or `NOT_REPRODUCIBLE` (disappeared).
  - Enforces clean state reset before every trial without reusing stale tokens or IDs.
- **Test Minimizer (`agent/minimizer.py`):**
  - **1-Minimal Sequence Delta Debugging:** Iteratively removes non-essential requests from multi-step reproduction sequences.
  - **Payload Field Delta Debugging:** Prunes optional, extraneous keys from JSON request bodies while preserving schema requirements.
  - **Bug Invariance:** Rejects candidate sequences if the exact target vulnerability (e.g. BOLA violation) is lost or if prerequisite data dependencies fail.
  - **Reduction Metric:** Calculates reduction ratio $1 - (\text{minimized} / \text{original})$. (e.g., reduces a 10-request noisy BOLA sequence to 4 essential requests, achieving a 60% reduction).

### 5.8 AI-Assisted Bug Diagnosis & Reporting (`agent/reporter.py`)
- **Structured AI Diagnosis (`AIDiagnosis`):**
  - Formulates plain-language root cause explanations clearly categorized as hypotheses (`hypothesis`), not confirmed facts.
  - Documents supporting observations (`supporting_evidence`), recommended verifications (`additional_checks`), and explicit limitations/unknowns (`uncertainties`).
  - Proposes actionable code remediation snippets matching actual project structure (e.g., checking `order["user_id"] != current_user["user_id"]` in `sample_api/main.py`).
- **Configurable LLM Client with Deterministic Fallback:**
  - `LLMDiagnoser` supports external providers (`LLM_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`).
  - Never hardcodes secrets; gracefully falls back to `RuleBasedDiagnoser` if no key is configured or upon network/timeout errors, noting the exact source without pretending an AI model was called.
- **Dual-Format Professional Bug Reports (`BugReport`):**
  - Exports comprehensive Markdown (`.md`) and machine-readable JSON (`.json`) files saved in `reports/`.
  - Includes executive summaries, verification metrics (Step 6), original vs minimized sequence reduction ratios, and full evidence dumps.
  - Guarantees strict redaction of sensitive credentials (`Authorization`, `tokens`, `passwords`).
- **Standalone Reproductions:**
  - Generates copy-pasteable Windows PowerShell commands using `Invoke-RestMethod`.
  - Generates standalone runnable pytest files (`reports/test_reproduce_bola.py`) that verify defects independently of the main agent framework.

