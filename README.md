# Autonomous AI Testing Agent for REST APIs

An AI-assisted system that automatically inspects, tests, and discovers bugs and security vulnerabilities (such as Broken Object Level Authorization) in REST APIs.

---

## Stage 1: Controlled Sample API

In this initial stage, we built an isolated, controlled target API representing an e-commerce shopping service. It provides user authentication, order management, interactive Swagger documentation, and a deterministic reset mechanism for reproducible test runs.

### Deliberate Vulnerability (BOLA)
The API includes an intentional **Broken Object Level Authorization (BOLA / IDOR)** vulnerability on `GET /orders/{order_id}` (OWASP API Security Top 10 - API1:2023):
- **Intended secure policy:** An authenticated user should only be allowed to view orders they personally created.
- **Flawed implementation:** The endpoint authenticates the caller, but omits the ownership validation check (`order.user_id == current_user.user_id`). As a result, **User Bob can read User Alice's private orders** simply by supplying Alice's `order_id`.

---

## Project Structure

```text
api_testing/
├── sample_api/
│   ├── __init__.py         # Package initializer
│   ├── config.py           # Configuration (Host, Port, Reset toggle)
│   ├── schemas.py          # Pydantic request and response models
│   ├── database.py         # In-memory storage & deterministic reset
│   ├── auth.py             # Demo credentials & Bearer token management
│   └── main.py             # FastAPI application and endpoints
├── tests/
│   ├── __init__.py         # Tests package
│   ├── conftest.py         # Pytest fixtures (clean database per test, TestClient)
│   └── test_sample_api.py  # 9 automated tests verifying functionality & BOLA bug
├── pytest.ini              # Pytest configuration
├── requirements.txt        # Python package dependencies
└── README.md               # Documentation and execution instructions
```

---

## Predefined Demo Users

| Username | Password | User ID | Role |
| :--- | :--- | :--- | :--- |
| `alice` | `alice123` | `user-alice` | Customer A |
| `bob` | `bob123` | `user-bob` | Customer B |

---

## API Endpoints

| Method | Path | Auth Required | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | No | System health check (`{"status": "ok"}`) |
| `POST` | `/auth/login` | No | Authenticate Alice or Bob, returns Bearer token |
| `POST` | `/orders` | Yes (Bearer) | Create a new order for the authenticated user |
| `GET` | `/orders/{order_id}` | Yes (Bearer) | **Vulnerable to BOLA**: Returns order without checking ownership |
| `POST` | `/admin/reset` | No (Local only) | Deterministically resets all orders and session tokens |
| `GET` | `/docs` | No | Interactive Swagger UI |
| `GET` | `/openapi.json` | No | OpenAPI 3.1 specification schema |

---

## Setup & Running on Windows (PowerShell)

### 1. Install Dependencies

Open Windows PowerShell in the project directory:

```powershell
python -m pip install -r requirements.txt
```

### 2. Start the Sample API

Start the local server bound to `127.0.0.1:8000`:

```powershell
python -m uvicorn sample_api.main:app --host 127.0.0.1 --port 8000 --reload
```

Once running:
- Open Swagger UI in your browser: `http://127.0.0.1:8000/docs`
- Inspect OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

---

## Running Automated Tests

Run pytest from the project root:

```powershell
pytest -v
```

All 9 test cases will execute:
1. `test_health_check`: Validates `/health`.
2. `test_login_success_both_users`: Confirms login tokens for Alice and Bob.
3. `test_login_invalid_credentials_rejected`: Validates 401 on bad credentials.
4. `test_unauthenticated_requests_rejected`: Validates 401 on missing tokens.
5. `test_alice_create_and_retrieve_own_order`: Normal order workflow for Alice.
6. `test_intentional_bola_bob_accesses_alice_order`: **Demonstrates and verifies the intentional BOLA vulnerability.**
7. `test_order_not_found`: Validates 404 on nonexistent order ID.
8. `test_deterministic_test_reset`: Validates `/admin/reset` cleans state and invalidates previous tokens.
9. `test_openapi_and_swagger_docs`: Confirms OpenAPI schema generation and `/docs`.

---

## Manual BOLA Bug Demonstration (PowerShell)

While the API server is running on `http://127.0.0.1:8000`, run the following commands in PowerShell to reproduce the vulnerability step-by-step:

```powershell
# 1. Alice logs in and receives her token
$aliceLogin = Invoke-RestMethod -Uri "http://127.0.0.1:8000/auth/login" -Method Post -ContentType "application/json" -Body '{"username":"alice","password":"alice123"}'
$aliceToken = $aliceLogin.access_token

# 2. Alice creates a private order
$orderBody = '{"item_name":"Private Diary & Vault","quantity":1,"total_price":79.99}'
$aliceOrder = Invoke-RestMethod -Uri "http://127.0.0.1:8000/orders" -Method Post -ContentType "application/json" -Headers @{ Authorization = "Bearer $aliceToken" } -Body $orderBody
$orderId = $aliceOrder.id
Write-Host "Created Alice's Order: $orderId"

# 3. Bob logs in and receives Bob's token
$bobLogin = Invoke-RestMethod -Uri "http://127.0.0.1:8000/auth/login" -Method Post -ContentType "application/json" -Body '{"username":"bob","password":"bob123"}'
$bobToken = $bobLogin.access_token

# 4. Bob exploits BOLA by querying Alice's order with Bob's token
$stolenOrder = Invoke-RestMethod -Uri "http://127.0.0.1:8000/orders/$orderId" -Method Get -Headers @{ Authorization = "Bearer $bobToken" }

# 5. Inspect the leaked data
Write-Host "Vulnerability Verified! Bob received Alice's order:"
$stolenOrder | Format-List
```
