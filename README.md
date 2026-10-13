# Autonomous AI Testing Agent for REST APIs

An AI-assisted system that automatically inspects, tests, and discovers bugs and security vulnerabilities (such as Broken Object Level Authorization) in REST APIs.

---

## Documentation

- **[PRD.md](PRD.md):** Complete Product Requirements Document covering project goals, modular architecture, and stage-by-stage implementation milestones.
- **[DECISIONS.md](DECISIONS.md):** Architectural Decision Records (ADRs) tracking foundational design and technical decisions.

---

## Roadmap Progress

- [x] **Step 1: Controlled Sample API** (FastAPI shopping API with auth, orders, and intentional BOLA bug)
- [x] **Step 2: OpenAPI Specification Reader** (Structured specification parser, reference resolver, and validator)
- [x] **Step 3: Request Executor** (HTTP client with path substitution, Bearer auth, redaction, and tracing)
- [x] **Step 4: Automatic Test Generation & Dependency Handling** (Schema synthesizer, mutation generator, NetworkX dependency graph, sequence runner, Schemathesis baseline)
- [x] **Step 5: Bug Detection & Security Oracles** (Server error oracle, schema conformance validator, BOLA cross-user security oracle)
- [x] **Step 6: Verification & Test Minimization** (Clean replay bug verifier, flakiness detection, delta-debugging test sequence minimizer)
- [ ] **Step 7: AI-Assisted Diagnosis & Reporting**
- [ ] **Step 8: Evaluation & Benchmark Comparisons**

---

## Project Structure

```text
api_testing/
├── PRD.md                      # Product Requirements Document
├── DECISIONS.md                # Architectural Decision Records (ADR)
├── README.md                   # Quickstart and execution guide
├── requirements.txt            # Python dependencies
├── pytest.ini                  # Pytest configuration
├── agent/
│   ├── __init__.py             # Agent package initializer
│   ├── spec_reader.py          # OpenAPI 3.x parser, $ref resolver & models
│   ├── executor.py             # HTTP request executor, redaction & trace recorder
│   ├── dependency_graph.py     # NetworkX dependency graph & sequence planner
│   ├── test_generator.py       # Normal/invalid test synthesis & sequence runner
│   ├── oracles.py              # Bug detection oracles (5xx, schema, BOLA security)
│   ├── verifier.py             # Clean-state replay & flakiness classification
│   └── minimizer.py            # Delta-debugging sequence & payload minimizer
├── sample_api/
│   ├── __init__.py             # Sample API package
│   ├── config.py               # Settings (Host, Port, Reset toggle)
│   ├── schemas.py              # Pydantic request and response models
│   ├── database.py             # In-memory storage & deterministic reset
│   ├── auth.py                 # Demo credentials & Bearer token management
│   ├── main.py                 # FastAPI application and endpoints
│   └── openapi.json            # Exported OpenAPI 3.1 specification
└── tests/
    ├── __init__.py             # Tests package
    ├── conftest.py             # Shared fixtures (clean state, TestClient)
    ├── test_sample_api.py      # 9 tests verifying sample API & intentional BOLA bug
    ├── test_spec_reader.py     # 16 tests verifying spec reader, parsing, $ref, errors
    ├── test_executor.py        # 13 tests verifying request execution, auth, redaction
    ├── test_dependency_graph.py# 6 tests verifying NetworkX graph & sequencing
    ├── test_generator.py       # 10 tests verifying normal/invalid generation & sequences
    ├── test_oracles.py         # 14 tests verifying server errors, schema violations & BOLA
    └── test_verifier_minimizer.py # 11 tests verifying verifier, delta debugging & live BOLA
```

---

## Stage 4: Test Generator & Dependency Handling

### 1. Automatic Test Generator (`agent/test_generator.py`)
- **Normal Tests:** Automatically synthesizes valid payloads matching OpenAPI schema types, enums, examples, and constraints, expecting documented 2xx status codes.
- **Invalid-Input Tests:** Systematically applies mutations:
  - Omits required fields (expecting 400 or 422).
  - Injects type mismatches, e.g. sending text for integer quantities (expecting 400 or 422).
  - Tests boundary violations, e.g. negative prices (expecting 400 or 422).
  - Tests unauthenticated requests on secured endpoints (expecting 401).

### 2. Dependency Graph (`agent/dependency_graph.py`)
- Uses NetworkX directed graphs (`DiGraph`) to model producer-consumer relationships:
  - Links operations requiring authentication to `POST /auth/login` (source: `access_token` -> target: `auth_token`).
  - Links resource consumers (e.g. `GET /orders/{order_id}`) to creators (`POST /orders`, source: `id` -> target: `order_id`).
- Automatically computes topological execution plans (`SequencePlan`).

### 3. Dependent Sequence Runner
- Executes multi-step workflows: `Login -> Create Order -> Retrieve Order`.
- Propagates dynamic values across requests (e.g., extracts token from login and order ID from order creation, passing both into order retrieval).

### 4. Schemathesis Baseline Integration
- Integrated Schemathesis 4.x property-based testing to provide comparative benchmark coverage.
- All Schemathesis test cases are explicitly labeled `[SCHEMATHESIS]` to distinguish them from custom agent-generated tests.

---

## Stage 5: Bug Detection & Security Oracles (`agent/oracles.py`)

The agent implements three deterministic behavioral oracles that inspect HTTP test results:

1. **Check 1: Server Error Oracle (`ServerErrorOracle`):**
   - Catches HTTP 5xx responses (500, 502, 503).
   - Records sanitized request details and response data as a suspicious/possible problem (`is_confirmed=False`) for investigation without prematurely asserting a bug.

2. **Check 2: Schema Conformance Oracle (`SchemaConformanceOracle`):**
   - Compares actual HTTP status codes and response bodies with the OpenAPI documentation.
   - Uses standard JSON Schema validation (`jsonschema`) to flag missing required fields, type mismatches (e.g. price returned as string), and undocumented status codes as confirmed contract violations (`is_confirmed=True`).
   - If expected behavior is not documented, does not invent rules.

3. **Check 3: BOLA Security Oracle (`BOLAOracle`):**
   - Tests for Broken Object Level Authorization (OWASP API1:2023):
     1. User Alice logs in and creates an order (`POST /orders`).
     2. User Bob logs in and attempts to retrieve Alice's order using Bob's Bearer token (`GET /orders/{order_id}`).
     3. Compares caller identity (`user-bob`) with resource owner (`user-alice`). If Bob receives Alice's private data, records a confirmed critical BOLA vulnerability with evidence.
     4. Runs a control check to ensure Alice accessing her own order is recognized as authorized and not flagged.

4. **Credential Redaction:**
   - All passwords, tokens, and `Authorization` headers are sanitized (`[REDACTED]`) before being recorded in finding evidence.

---

## Stage 6: Bug Verification & Test Minimization (`agent/verifier.py`, `agent/minimizer.py`)

1. **Bug Verifier (`agent/verifier.py`):**
   - Resets state and replays candidate bug scenarios at least twice (`repeat_count >= 2`).
   - Categorizes findings into `CONFIRMED_REPRODUCIBLE`, `FLAKY`, or `NOT_REPRODUCIBLE`.
   - Never reuses old credentials or resource IDs across replay runs.

2. **Test Minimizer (`agent/minimizer.py`):**
   - Applies Delta Debugging (1-minimal deletion pass) on failing multi-step request sequences.
   - Removes unnecessary intermediate requests (e.g. redundant health checks).
   - Prunes non-essential fields from JSON request bodies (e.g. optional notes).
   - Preserves core data dependencies and the exact target vulnerability.
   - Computes reduction metrics:
     $$\text{Reduction Ratio} = 1 - \left(\frac{\text{Minimized Requests}}{\text{Original Requests}}\right)$$

---

## Setup & Running on Windows (VS Code / PowerShell)

Open the project folder in VS Code. Open **Terminal → New Terminal** (PowerShell).

### 1. Install Dependencies

```powershell
python -m pip install -r requirements.txt
```

### 2. Start the Sample API (Terminal 1)

```powershell
python -m uvicorn sample_api.main:app --host 127.0.0.1 --port 8000 --reload
```

- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

### 3. Run Bug Verification (Terminal 2)

```powershell
python -m agent.verifier http://127.0.0.1:8000
```

### 4. Run Test Minimization (Terminal 2)

```powershell
python -m agent.minimizer http://127.0.0.1:8000
```

### 5. Run All Automated Tests

Run all 79 automated tests across all 6 stages:

```powershell
pytest -v
```

Or run tests by module:

```powershell
# Step 6 Verification and Minimization (11 tests)
pytest tests/test_verifier_minimizer.py -v

# Step 5 Bug Detection Oracles & BOLA (14 tests)
pytest tests/test_oracles.py -v

# Step 4 Test Generation and Sequences (16 tests)
pytest tests/test_generator.py tests/test_dependency_graph.py -v

# Step 3 Request Executor (13 tests)
pytest tests/test_executor.py -v

# Step 2 OpenAPI Specification Reader (16 tests)
pytest tests/test_spec_reader.py -v

# Step 1 Sample API and BOLA Bug (9 tests)
pytest tests/test_sample_api.py -v
```
