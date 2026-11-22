"""Automated tests for the Sample Shopping API.

Verifies:
1. Health check functionality
2. Authentication workflows for Alice and Bob
3. Credential rejection for invalid users
4. Authorized order creation and retrieval
5. Intentional BOLA vulnerability (Bob accessing Alice's order)
6. State reset endpoint behavior
7. OpenAPI and Swagger UI endpoint availability
"""

from fastapi.testclient import TestClient


def test_health_check(client: TestClient):
    """GET /health must return 200 OK and health status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "Sample Shopping API" in data["app"]


def test_login_success_both_users(client: TestClient):
    """Both Alice and Bob must be able to log in successfully and receive tokens."""
    # Alice login
    resp_alice = client.post("/auth/login", json={"username": "alice", "password": "alice123"})
    assert resp_alice.status_code == 200
    data_alice = resp_alice.json()
    assert "access_token" in data_alice
    assert data_alice["user_id"] == "user-alice"
    assert data_alice["username"] == "alice"

    # Bob login
    resp_bob = client.post("/auth/login", json={"username": "bob", "password": "bob123"})
    assert resp_bob.status_code == 200
    data_bob = resp_bob.json()
    assert "access_token" in data_bob
    assert data_bob["user_id"] == "user-bob"
    assert data_bob["username"] == "bob"


def test_login_invalid_credentials_rejected(client: TestClient):
    """Invalid passwords and non-existent users must be rejected with 401."""
    # Invalid password
    resp1 = client.post("/auth/login", json={"username": "alice", "password": "wrongpassword"})
    assert resp1.status_code == 401
    assert "Invalid username or password" in resp1.json()["detail"]

    # Non-existent user
    resp2 = client.post("/auth/login", json={"username": "charlie", "password": "password"})
    assert resp2.status_code == 401
    assert "Invalid username or password" in resp2.json()["detail"]


def test_unauthenticated_requests_rejected(client: TestClient):
    """Accessing protected endpoints without a token must return 401 Unauthorized."""
    # POST /orders without token
    resp_post = client.post("/orders", json={"item_name": "Book", "quantity": 1, "total_price": 10.0})
    assert resp_post.status_code == 401

    # GET /orders/ord-1 without token
    resp_get = client.get("/orders/ord-1")
    assert resp_get.status_code == 401


def test_alice_create_and_retrieve_own_order(client: TestClient):
    """Alice logs in, creates an order, and can view her own order."""
    # 1. Login Alice
    login_resp = client.post("/auth/login", json={"username": "alice", "password": "alice123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create order
    order_payload = {"item_name": "Mechanical Keyboard", "quantity": 1, "total_price": 99.50}
    create_resp = client.post("/orders", json=order_payload, headers=headers)
    assert create_resp.status_code == 201
    order_data = create_resp.json()
    order_id = order_data["id"]
    assert order_id == "ord-1"
    assert order_data["user_id"] == "user-alice"
    assert order_data["item_name"] == "Mechanical Keyboard"

    # 3. Retrieve own order
    get_resp = client.get(f"/orders/{order_id}", headers=headers)
    assert get_resp.status_code == 200
    retrieved = get_resp.json()
    assert retrieved["id"] == order_id
    assert retrieved["user_id"] == "user-alice"
    assert retrieved["item_name"] == "Mechanical Keyboard"


def test_intentional_bola_bob_accesses_alice_order(client: TestClient):
    """Demonstrate and verify the intentional Broken Object Level Authorization (BOLA) bug.

    Alice creates a private order. Bob logs in with his own credentials.
    In a secure API, Bob should receive HTTP 403 Forbidden when requesting Alice's order.
    Due to the intentional vulnerability in GET /orders/{order_id}, Bob receives HTTP 200 OK
    and gets full access to Alice's order.
    """
    # 1. Alice logs in and creates an order
    alice_login = client.post("/auth/login", json={"username": "alice", "password": "alice123"})
    alice_token = alice_login.json()["access_token"]
    alice_headers = {"Authorization": f"Bearer {alice_token}"}

    create_resp = client.post(
        "/orders",
        json={"item_name": "Noise Cancelling Headphones", "quantity": 1, "total_price": 250.0},
        headers=alice_headers,
    )
    assert create_resp.status_code == 201
    alice_order_id = create_resp.json()["id"]

    # 2. Bob logs in with Bob's credentials
    bob_login = client.post("/auth/login", json={"username": "bob", "password": "bob123"})
    assert bob_login.status_code == 200
    bob_token = bob_login.json()["access_token"]
    bob_headers = {"Authorization": f"Bearer {bob_token}"}

    # 3. Bob queries Alice's order ID
    bob_resp = client.get(f"/orders/{alice_order_id}", headers=bob_headers)

    # VULNERABILITY ASSERTION:
    # A secure API would return 403 Forbidden.
    # Our intentionally vulnerable API returns 200 OK, leaking Alice's order to Bob!
    assert bob_resp.status_code == 200
    bob_viewed_order = bob_resp.json()
    assert bob_viewed_order["id"] == alice_order_id
    assert bob_viewed_order["user_id"] == "user-alice"
    assert bob_viewed_order["item_name"] == "Noise Cancelling Headphones"


def test_order_not_found(client: TestClient):
    """Accessing a non-existent order ID returns 404 Not Found."""
    login_resp = client.post("/auth/login", json={"username": "alice", "password": "alice123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/orders/nonexistent-id", headers=headers)
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_deterministic_test_reset(client: TestClient):
    """The /admin/reset endpoint clears all orders and active tokens."""
    # 1. Alice logs in and creates an order
    alice_login = client.post("/auth/login", json={"username": "alice", "password": "alice123"})
    token = alice_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = client.post(
        "/orders",
        json={"item_name": "Smart Watch", "quantity": 1, "total_price": 199.99},
        headers=headers,
    )
    assert create_resp.status_code == 201
    order_id = create_resp.json()["id"]

    # 2. Trigger test reset
    reset_resp = client.post("/admin/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json()["status"] == "reset"

    # 3. Old token should now be invalid
    old_token_resp = client.get(f"/orders/{order_id}", headers=headers)
    assert old_token_resp.status_code == 401

    # 4. Logging back in with fresh token shows the previous order no longer exists
    fresh_login = client.post("/auth/login", json={"username": "alice", "password": "alice123"})
    fresh_headers = {"Authorization": f"Bearer {fresh_login.json()['access_token']}"}
    check_resp = client.get(f"/orders/{order_id}", headers=fresh_headers)
    assert check_resp.status_code == 404


def test_openapi_and_swagger_docs(client: TestClient):
    """Verify that OpenAPI JSON and Swagger UI endpoints are fully functional."""
    # OpenAPI JSON specification
    openapi_resp = client.get("/openapi.json")
    assert openapi_resp.status_code == 200
    schema = openapi_resp.json()
    assert "openapi" in schema
    assert "paths" in schema
    assert "/health" in schema["paths"]
    assert "/auth/login" in schema["paths"]
    assert "/orders" in schema["paths"]
    assert "/orders/{order_id}" in schema["paths"]
    assert "/admin/reset" in schema["paths"]

    # Swagger UI documentation page
    docs_resp = client.get("/docs")
    assert docs_resp.status_code == 200
    assert "text/html" in docs_resp.headers["content-type"]
