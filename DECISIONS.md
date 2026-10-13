# Architectural Decision Records (ADR) & Key Project Decisions

This document records the foundational and ongoing architectural decisions made during the design and construction of the **Autonomous AI Testing Agent for REST APIs**. Any future design changes, compromises, and architectural pivots should be recorded here.

---

## Decision Index

1. [ADR-001: Strict Separation of Target API and Testing Agent](#adr-001-strict-separation-of-target-api-and-testing-agent)
2. [ADR-002: In-Memory Storage with Deterministic Reset Endpoint](#adr-002-in-memory-storage-with-deterministic-reset-endpoint)
3. [ADR-003: Isolated BOLA Vulnerability Implementation](#adr-003-isolated-bola-vulnerability-implementation)
4. [ADR-004: Pydantic Data Models with Internal Reference ($ref) Resolution](#adr-004-pydantic-data-models-with-internal-reference-ref-resolution)
5. [ADR-005: Resilient Request Execution without Agent Crashes](#adr-005-resilient-request-execution-without-agent-crashes)
6. [ADR-006: Mandatory Credential and Token Redaction in Traces](#adr-006-mandatory-credential-and-token-redaction-in-traces)
7. [ADR-007: Dependency Representation via NetworkX Directed Graph](#adr-007-dependency-representation-via-networkx-directed-graph)
8. [ADR-008: Schema-Driven Test Generation Strategy](#adr-008-schema-driven-test-generation-strategy)
9. [ADR-009: Schemathesis Complementary Integration](#adr-009-schemathesis-complementary-integration)
10. [ADR-010: Windows Console and Encoding Compatibility](#adr-010-windows-console-and-encoding-compatibility)
11. [ADR-011: Multi-Tiered Bug Oracles & Suspicious vs Confirmed Findings](#adr-011-multi-tiered-bug-oracles--suspicious-vs-confirmed-findings)
12. [ADR-012: Deterministic BOLA Cross-User Security Oracle](#adr-012-deterministic-bola-cross-user-security-oracle)

---

### ADR-001: Strict Separation of Target API and Testing Agent
- **Status:** Accepted (Step 1)
- **Context:** The testing agent will eventually test third-party or remote APIs. If the agent relied on internal Python function imports or database coupling, it would not simulate real-world testing.
- **Decision:** The sample shopping API is strictly isolated inside `sample_api/`. All interactions by the agent are conducted over HTTP via `agent/executor.py`.
- **Consequence:** The agent can be pointed at any external API simply by supplying its base URL and OpenAPI schema.

---

### ADR-002: In-Memory Storage with Deterministic Reset Endpoint
- **Status:** Accepted (Step 1)
- **Context:** Reproducibility and minimization (Steps 5 and 6) require clean, repeatable test states between runs.
- **Decision:** The sample API stores orders and tokens in in-memory dictionaries. A dedicated endpoint `POST /admin/reset` was implemented, guarded by the `ENABLE_TEST_RESET` environment flag, to reset data and tokens deterministically.
- **Consequence:** Automated tests and future minimization algorithms can restore pristine state in milliseconds without spinning up external database containers.

---

### ADR-003: Isolated BOLA Vulnerability Implementation
- **Status:** Accepted (Step 1)
- **Context:** To evaluate the agent's ability to detect authorization vulnerabilities, the API must contain a known flaw while remaining safe and predictable.
- **Decision:** An intentional Broken Object Level Authorization (BOLA / IDOR) vulnerability was placed exclusively on `GET /orders/{order_id}`. The endpoint verifies authentication, but omits the ownership check (`order["user_id"] == current_user["user_id"]`).
- **Consequence:** Provides a clear benchmark target for security oracles (Step 5) where User Bob can access User Alice's private order.

---

### ADR-004: Pydantic Data Models with Internal Reference ($ref) Resolution
- **Status:** Accepted (Step 2)
- **Context:** OpenAPI schemas frequently use `$ref` pointers (e.g. `#/components/schemas/OrderResponse`). Unresolved references make automated test generation and validation difficult.
- **Decision:** `agent/spec_reader.py` parses OpenAPI 3.0.x and 3.1.x documents into strongly-typed Pydantic models. It includes a deep pointer resolver for `#/...` references that detects and handles circular schemas without infinite recursion. External network references are disallowed.
- **Consequence:** Downstream modules receive fully resolved parameter, body, and response schemas.

---

### ADR-005: Resilient Request Execution without Agent Crashes
- **Status:** Accepted (Step 3)
- **Context:** Test generators and fuzzers frequently trigger connection timeouts, unreachable ports, or malformed responses. If an HTTP failure crashed the process, the entire test suite would halt.
- **Decision:** `agent/executor.py` catches `httpx.ConnectError`, `httpx.TimeoutException`, and protocol errors, converting them into structured `ExecutionResult(has_error=True, error_type=...)` objects.
- **Consequence:** The testing agent continues executing and evaluating subsequent test cases regardless of network or protocol failures.

---

### ADR-006: Mandatory Credential and Token Redaction in Traces
- **Status:** Accepted (Step 3)
- **Context:** Test traces and logs are stored, serialized, and eventually passed to reports and LLMs. Storing raw tokens and passwords poses significant credential leakage risks.
- **Decision:** Recursive sanitizers (`redact_headers` and `redact_payload`) automatically replace values for keys like `Authorization`, `Cookie`, `password`, `token`, and `secret` with `[REDACTED]`.
- **Consequence:** Stored traces and logs can be safely exported and presented without exposing sensitive credentials.

---

### ADR-007: Dependency Representation via NetworkX Directed Graph
- **Status:** Accepted (Step 4)
- **Context:** Endpoints depend on outputs from previous requests (e.g., `POST /auth/login` produces `access_token`; `POST /orders` produces `id`). We need to execute operations in correct prerequisite order.
- **Decision:** `agent/dependency_graph.py` builds a `networkx.DiGraph` where nodes represent endpoints and edges represent data dependencies (`source_field` -> `target_field`). Topological sorting produces execution sequence plans.
- **Consequence:** Enables dynamic test sequence plans (`Login -> Create Order -> Get Order`) where dynamic response values are captured and passed to subsequent steps.

---

### ADR-008: Schema-Driven Test Generation Strategy
- **Status:** Accepted (Step 4)
- **Context:** Manual test writing doesn't scale. The agent must create meaningful positive and negative test cases directly from specification constraints.
- **Decision:** `agent/test_generator.py` uses JSON schemas to generate:
  - **Normal tests:** Valid values derived from examples, enums, types, and defaults, expecting documented 2xx responses.
  - **Invalid-input tests:** Systematic mutations: omitting required fields (expecting 400/422), injecting type mismatches (expecting 400/422), constraint violations (negative numbers, expecting 400/422), and missing authentication (expecting 401).
- **Consequence:** High-coverage deterministic test suite generated automatically without hardcoded endpoint knowledge.

---

### ADR-009: Schemathesis Complementary Integration
- **Status:** Accepted (Step 4)
- **Context:** Schemathesis is an industry-standard property-based API testing tool. We want its fuzzing strengths without sacrificing our custom dependency sequencing and BOLA oracles.
- **Decision:** Schemathesis 4.x is integrated as a complementary baseline runner (`run_schemathesis_baseline`). All its tests are clearly tagged `[SCHEMATHESIS]` to distinguish them from agent-generated tests (`[AGENT]`).
- **Consequence:** Enables baseline comparisons without replacing our custom sequence planning and oracle pipeline.

---

### ADR-010: Windows Console and Encoding Compatibility
- **Status:** Accepted (Step 2 & 3)
- **Context:** Windows PowerShell consoles with standard `cp1252` encoding crash when attempting to print Unicode emojis (such as padlock icons) or unsupported bullet characters.
- **Decision:** All CLI outputs, logs, and error messages use standard ASCII formatting (`[AUTH]`, `[PUBLIC]`, `*`). Pytest test classes inside agent modules define `__test__ = False` to prevent collection warnings.
- **Consequence:** Flawless cross-platform execution on Windows without encoding exceptions.

---

### ADR-011: Multi-Tiered Bug Oracles & Suspicious vs Confirmed Findings
- **Status:** Accepted (Step 5)
- **Context:** An autonomous testing agent must classify defects with clear evidence. Labeling all anomalies as confirmed bugs produces noise, while ignoring 5xx responses hides unhandled exceptions.
- **Decision:** Implement dedicated oracles in `agent/oracles.py`:
  - `ServerErrorOracle`: Catches HTTP 5xx responses and tags them as suspicious/possible problems (`is_confirmed=False`), recording full sanitized request/response context for later replay verification (Step 6).
  - `SchemaConformanceOracle`: Evaluates response payloads against OpenAPI schemas using `jsonschema`. Flags missing required properties, type mismatches (e.g. price as string), and undocumented status codes as confirmed contract violations (`is_confirmed=True`). If behavior is not documented, does not invent rules.
- **Consequence:** Provides clear differentiation between potential server crashes (requiring verification) and explicit specification violations.

---

### ADR-012: Deterministic BOLA Cross-User Security Oracle
- **Status:** Accepted (Step 5)
- **Context:** Broken Object Level Authorization (BOLA / OWASP API1:2023) is the #1 API security vulnerability. Testing for it requires a stateful cross-tenant interaction: User Alice creates a private resource, and User Bob attempts to access it.
- **Decision:** `BOLAOracle` implements a deterministic test sequence and an individual evaluation rule:
  1. Compares caller user ID against the resource owner's user ID.
  2. If caller is NOT the owner and the response is HTTP 200 with Alice's object, flags a critical confirmed `BOLA_VIOLATION` (`is_confirmed=True`).
  3. Includes a control check: Alice accessing her own order is confirmed authorized and never flagged.
  4. Redacts all authentication tokens and passwords from evidence.
- **Consequence:** Reliable, automated security verification that uncovers object authorization bugs with zero false positives on authorized owner accesses.

