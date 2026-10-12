"""Pydantic request and response models for the Sample Shopping API."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(default="ok", examples=["ok"])
    app: str = Field(default="Sample Shopping API", examples=["Sample Shopping API"])
    version: str = Field(default="1.0.0", examples=["1.0.0"])


class LoginRequest(BaseModel):
    """User login credentials."""

    username: str = Field(..., description="Demo username ('alice' or 'bob')", examples=["alice"])
    password: str = Field(..., description="Demo password ('alice123' or 'bob123')", examples=["alice123"])


class TokenResponse(BaseModel):
    """Authentication token response."""

    access_token: str = Field(..., description="Bearer token to include in the Authorization header")
    token_type: str = Field(default="bearer", description="Token type")
    user_id: str = Field(..., description="Unique user identifier")
    username: str = Field(..., description="Username of the authenticated user")


class OrderCreate(BaseModel):
    """Schema for creating a new order."""

    item_name: str = Field(..., min_length=1, description="Name of the item purchased", examples=["Wireless Headphones"])
    quantity: int = Field(..., gt=0, description="Quantity of items (must be > 0)", examples=[2])
    total_price: float = Field(..., ge=0.0, description="Total order price (must be >= 0)", examples=[59.98])


class OrderResponse(BaseModel):
    """Schema for order details."""

    id: str = Field(..., description="Unique identifier for the order", examples=["ord-1"])
    user_id: str = Field(..., description="ID of the user who owns this order", examples=["user-alice"])
    item_name: str = Field(..., description="Name of the item purchased", examples=["Wireless Headphones"])
    quantity: int = Field(..., description="Quantity of items", examples=[2])
    total_price: float = Field(..., description="Total price", examples=[59.98])
    status: str = Field(default="pending", description="Order status", examples=["pending"])
    created_at: str = Field(..., description="ISO 8601 creation timestamp", examples=["2026-10-12T12:00:00Z"])


class ResetResponse(BaseModel):
    """Response returned when test state is reset."""

    status: str = Field(default="reset", examples=["reset"])
    message: str = Field(default="Test database reset to initial state", examples=["Test database reset to initial state"])
