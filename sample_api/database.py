"""In-memory data store for the Sample Shopping API.

Provides deterministic data management and clean resets for test environments.
"""

from typing import Dict, Optional, Any
from copy import deepcopy

# Predefined local demo users
DEMO_USERS: Dict[str, Dict[str, str]] = {
    "alice": {
        "user_id": "user-alice",
        "username": "alice",
        "password": "alice123",
        "email": "alice@example.com",
    },
    "bob": {
        "user_id": "user-bob",
        "username": "bob",
        "password": "bob123",
        "email": "bob@example.com",
    },
}

# In-memory storage for orders: order_id -> order dict
_orders: Dict[str, Dict[str, Any]] = {}
_order_counter: int = 0


def get_user_by_username(username: str) -> Optional[Dict[str, str]]:
    """Look up a demo user by username."""
    return DEMO_USERS.get(username.lower())


def get_user_by_id(user_id: str) -> Optional[Dict[str, str]]:
    """Look up a demo user by user ID."""
    for user in DEMO_USERS.values():
        if user["user_id"] == user_id:
            return user
    return None


def create_order(user_id: str, item_name: str, quantity: int, total_price: float) -> Dict[str, Any]:
    """Create and store a new order with an incremental deterministic ID."""
    global _order_counter
    _order_counter += 1
    order_id = f"ord-{_order_counter}"
    
    order = {
        "id": order_id,
        "user_id": user_id,
        "item_name": item_name,
        "quantity": quantity,
        "total_price": total_price,
        "status": "pending",
        "created_at": "2026-10-12T12:00:00Z",
    }
    _orders[order_id] = order
    return deepcopy(order)


def get_order(order_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve an order by ID."""
    order = _orders.get(order_id)
    return deepcopy(order) if order else None


def list_orders() -> Dict[str, Dict[str, Any]]:
    """Return all orders in memory."""
    return deepcopy(_orders)


def reset_db() -> None:
    """Reset the database state back to initial clean state."""
    global _order_counter, _orders
    _orders.clear()
    _order_counter = 0
