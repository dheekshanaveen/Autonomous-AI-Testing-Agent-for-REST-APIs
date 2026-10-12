"""Pydantic request and response models for the Sample Shopping API."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(default="ok", example="ok")
    app: str = Field(default="Sample Shopping API", example="Sample Shopping API")
    version: str = Field(default="1.0.0", example="1.0.0")


class LoginRequest(BaseModel):
    """User login credentials."""

    username: str = Field(..., description="Demo username ('alice' or 'bob')", example="alice")
    password: str = Field(..., description="Demo password ('alice123' or 'bob123')", example="alice123")


class TokenResponse(BaseModel):
    """Authentication token response."""

    access_token: str = Field(..., description="Bearer token to include in the Authorization header")
    token_type: str = Field(default="bearer", description="Token type")
    user_id: str = Field(..., description="Unique user identifier")
    username: str = Field(..., description="Username of the authenticated user")


class OrderCreate(BaseModel):
    """Schema for creating a new order."""

    item_name: str = Field(..., min_length=1, description="Name of the item purchased", example="Wireless Headphones")
    quantity: int = Field(..., gt=0, description="Quantity of items (must be > 0)", example=2)
    total_price: float = Field(..., ge=0.0, description="Total order price (must be >= 0)", example=59.98)


class OrderResponse(BaseModel):
    """Schema for order details."""

    id: str = Field(..., description="Unique identifier for the order", example="ord-1")
    user_id: str = Field(..., description="ID of the user who owns this order", example="user-alice")
    item_name: str = Field(..., description="Name of the item purchased", example="Wireless Headphones")
    quantity: int = Field(..., description="Quantity of items", example=2)
    total_price: float = Field(..., description="Total price", example=59.98)
    status: str = Field(default="pending", description="Order status", example="pending")
    created_at: str = Field(..., description="ISO 8601 creation timestamp", example="2026-10-12T12:00:00Z")


class ResetResponse(BaseModel):
    """Response returned when test state is reset."""

    status: str = Field(default="reset", example="reset")
    message: str = Field(default="Test database reset to initial state", example="Test database reset to initial state")
