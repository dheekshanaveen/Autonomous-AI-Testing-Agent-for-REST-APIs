"""FastAPI application for the Sample Shopping API.

This API serves as a controlled, isolated target for autonomous API testing.
It includes a deliberate Broken Object Level Authorization (BOLA) vulnerability
on the GET /orders/{order_id} endpoint for security oracle evaluation.
"""

from typing import Dict
from fastapi import FastAPI, Depends, HTTPException, status

from sample_api.config import settings
from sample_api.schemas import (
    HealthResponse,
    LoginRequest,
    TokenResponse,
    OrderCreate,
    OrderResponse,
    ResetResponse,
)
from sample_api.database import (
    create_order,
    get_order,
    reset_db,
)
from sample_api.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    reset_auth,
)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "A controlled, isolated shopping API built for autonomous API testing experiments.\n\n"
        "**Demo credentials:**\n"
        "- Alice: `alice` / `alice123`\n"
        "- Bob: `bob` / `bob123`\n\n"
        "**Notice:** Contains an intentional BOLA vulnerability on `GET /orders/{order_id}`."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="System health check",
    description="Returns a simple health status to verify the API is running.",
)
def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
    )


@app.post(
    "/auth/login",
    response_model=TokenResponse,
    tags=["Authentication"],
    summary="Authenticate demo user",
    description="Authenticates local demo users (Alice or Bob) and returns a Bearer access token.",
)
def login(creds: LoginRequest) -> TokenResponse:
    user = authenticate_user(creds.username, creds.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )
    token = create_access_token(user["user_id"])
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=user["user_id"],
        username=user["username"],
    )


@app.post(
    "/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Orders"],
    summary="Create a new order",
    description="Creates an order for the currently authenticated user.",
)
def create_new_order(
    order_in: OrderCreate,
    current_user: Dict[str, str] = Depends(get_current_user),
) -> OrderResponse:
    order = create_order(
        user_id=current_user["user_id"],
        item_name=order_in.item_name,
        quantity=order_in.quantity,
        total_price=order_in.total_price,
    )
    return OrderResponse(**order)


@app.get(
    "/orders/{order_id}",
    response_model=OrderResponse,
    tags=["Orders"],
    summary="Get an order by ID",
    description=(
        "Retrieve order details by order_id. Requires Bearer authentication.\n\n"
        "⚠️ **VULNERABILITY NOTE (OWASP API1:2023 - BOLA):** This endpoint authenticates the "
        "caller but intentionally does not check whether the authenticated user owns this order. "
        "Any authenticated user can access any other user's order."
    ),
)
def get_order_by_id(
    order_id: str,
    current_user: Dict[str, str] = Depends(get_current_user),
) -> OrderResponse:
    order = get_order(order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found.",
        )

    # --------------------------------------------------------------------------
    # INTENTIONAL BOLA VULNERABILITY (Broken Object Level Authorization):
    # In a secure implementation, we would verify ownership:
    #     if order["user_id"] != current_user["user_id"]:
    #         raise HTTPException(status_code=403, detail="Forbidden: Not your order")
    #
    # We deliberately omit this check so that Bob can inspect Alice's order.
    # --------------------------------------------------------------------------

    return OrderResponse(**order)


@app.post(
    "/admin/reset",
    response_model=ResetResponse,
    tags=["Testing & Admin"],
    summary="Reset test database state",
    description="Resets all orders and active sessions. Only available when ENABLE_TEST_RESET is True.",
)
def reset_test_state() -> ResetResponse:
    if not settings.ENABLE_TEST_RESET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reset endpoint is disabled in this environment.",
        )
    reset_db()
    reset_auth()
    return ResetResponse(
        status="reset",
        message="Database and session state successfully reset to initial clean state.",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("sample_api.main:app", host=settings.HOST, port=settings.PORT, reload=True)
