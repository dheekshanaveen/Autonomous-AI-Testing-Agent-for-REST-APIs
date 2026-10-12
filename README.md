# Autonomous AI Testing Agent for REST APIs

An AI-assisted system that automatically inspects, tests, and discovers bugs and security vulnerabilities (such as Broken Object Level Authorization) in REST APIs.

---

## Roadmap Progress

- [x] **Step 1: Controlled Sample API** (FastAPI shopping API with auth, orders, and intentional BOLA bug)
- [x] **Step 2: OpenAPI Specification Reader** (Structured specification parser, reference resolver, and validator)
- [ ] **Step 3: Request Executor**
- [ ] **Step 4: Basic Test Generation & Dependency Handling**
- [ ] **Step 5: Bug Detection & Security Oracles**
- [ ] **Step 6: Verification & Test Minimization**
- [ ] **Step 7: AI-Assisted Diagnosis & Reporting**
- [ ] **Step 8: Evaluation & Benchmark Comparisons**

---

## Project Structure

```text
api_testing/
├── agent/
│   ├── __init__.py             # Agent package initializer
│   └── spec_reader.py          # OpenAPI 3.x parser, $ref resolver & data models
├── sample_api/
│   ├── __init__.py             # Sample API package
│   ├── config.py               # Settings (Host, Port, Reset toggle)
│   ├── schemas.py              # Pydantic request and response models
│   ├── database.py             # In-memory storage & deterministic reset
│   ├── auth.py                 # Demo credentials & Bearer token management
│   ├── main.py                 # FastAPI application and endpoints
│   └── openapi.json            # Exported OpenAPI 3.1 specification
├── tests/
│   ├── __init__.py             # Tests package
│   ├── conftest.py             # Fixtures (clean database per test, TestClient)
│   ├── test_sample_api.py      # 9 tests verifying sample API & intentional BOLA bug
│   └── test_spec_reader.py     # 16 tests verifying spec reader, parsing, $ref, errors
├── pytest.ini                  # Pytest configuration
├── requirements.txt            # Python package dependencies
└── README.md                   # Documentation and execution instructions
```

---

## Stage 1: Controlled Sample API

The sample API models an e-commerce shopping service:
- Predefined local demo users: `alice` (`alice123`) and `bob` (`bob123`).
- Authenticates users and returns Bearer tokens.
- Allows authenticated users to create orders.
- **Intentional BOLA Vulnerability:** `GET /orders/{order_id}` authenticates the user, but omits ownership validation (`order.user_id == current_user.user_id`). As a result, User Bob can retrieve User Alice's private order by simply providing Alice's `order_id`.
- **Deterministic Reset:** `POST /admin/reset` clears all orders and active tokens for repeatable test states.

---

## Stage 2: OpenAPI Specification Reader (`agent/spec_reader.py`)

The specification reader reads an OpenAPI 3.0.x or 3.1.x document from an active URL (`http://127.0.0.1:8000/openapi.json`), a local file (`sample_api/openapi.json`), or an in-memory dictionary.

### Key Capabilities
1. **Endpoint Discovery:** Extracts all paths and operations (`GET /health`, `POST /auth/login`, `POST /orders`, `GET /orders/{order_id}`, `POST /admin/reset`).
2. **Parameter Extraction:** Identifies path, query, header, and cookie parameters, tracking required status and types.
3. **Request Body Parsing:** Identifies accepted media types (e.g. `application/json`), required flags, and resolved JSON schemas.
4. **Response Parsing:** Maps status codes (`200`, `201`, `422`), descriptions, content types, and resolved schemas.
5. **Component Reference Resolution (`$ref`):** Follows internal JSON pointers (e.g. `#/components/schemas/OrderResponse`), handles nested schemas, and protects against circular schema definitions.
6. **Authentication Extraction:** Parses `components.securitySchemes` (such as `HTTPBearer`) and operation-specific or global security requirements.
7. **Explicit Dependency / Link Extraction:** Extracts explicit OpenAPI links defined on responses (`operationId`, `parameters`).
8. **Robust Error Handling:** Distinguishes between connection failures (`SpecConnectionError`), missing files (`SpecNotFoundError`), invalid JSON (`SpecParseError`), missing OpenAPI structural fields (`SpecValidationError`), and unresolved pointers (`SpecResolutionError`).

---

## Setup & Running on Windows (PowerShell)

### 1. Install Dependencies

```powershell
python -m pip install -r requirements.txt
```

### 2. Start the Sample API

Start the server on `127.0.0.1:8000`:

```powershell
python -m uvicorn sample_api.main:app --host 127.0.0.1 --port 8000 --reload
```

- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

### 3. Run the Specification Reader

You can run the specification reader directly from the command line against the local JSON file (no server needed):

```powershell
python -m agent.spec_reader sample_api/openapi.json
```

Or run it against the live server URL when the server is running:

```powershell
python -m agent.spec_reader http://127.0.0.1:8000/openapi.json
```

---

## Running Automated Tests

Run all 25 automated tests across both stages:

```powershell
pytest -v
```

To run only the Step 2 specification reader tests:

```powershell
pytest tests/test_spec_reader.py -v
```

To run only the Step 1 sample API tests:

```powershell
pytest tests/test_sample_api.py -v
```

---

## Reproducing the Deliberate BOLA Bug Manually

While the API server is running on `http://127.0.0.1:8000`, run this script in PowerShell:

```powershell
# 1. Alice logs in
$aliceLogin = Invoke-RestMethod -Uri "http://127.0.0.1:8000/auth/login" -Method Post -ContentType "application/json" -Body '{"username":"alice","password":"alice123"}'
$aliceToken = $aliceLogin.access_token

# 2. Alice creates a private order
$orderBody = '{"item_name":"Private Security Vault","quantity":1,"total_price":79.99}'
$aliceOrder = Invoke-RestMethod -Uri "http://127.0.0.1:8000/orders" -Method Post -ContentType "application/json" -Headers @{ Authorization = "Bearer $aliceToken" } -Body $orderBody
$orderId = $aliceOrder.id
Write-Host "Created Alice's Order: $orderId"

# 3. Bob logs in
$bobLogin = Invoke-RestMethod -Uri "http://127.0.0.1:8000/auth/login" -Method Post -ContentType "application/json" -Body '{"username":"bob","password":"bob123"}'
$bobToken = $bobLogin.access_token

# 4. Bob exploits BOLA by querying Alice's order with Bob's token
$stolenOrder = Invoke-RestMethod -Uri "http://127.0.0.1:8000/orders/$orderId" -Method Get -Headers @{ Authorization = "Bearer $bobToken" }

# 5. Inspect leaked data
Write-Host "Vulnerability Verified! Bob received Alice's order:"
$stolenOrder | Format-List
```
