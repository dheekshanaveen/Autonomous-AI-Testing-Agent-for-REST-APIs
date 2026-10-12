"""Authentication utilities and session management for demo users."""

import uuid
from typing import Dict, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from sample_api.database import get_user_by_username, get_user_by_id

# FastAPI Bearer security scheme for OpenAPI documentation
security_bearer = HTTPBearer(
    auto_error=False,
    description="Provide your Bearer token received from /auth/login",
)

# Active session tokens map: token -> user_id
_active_tokens: Dict[str, str] = {}


def create_access_token(user_id: str) -> str:
    """Issue a new session token for the user."""
    token = f"demo-token-{user_id}-{uuid.uuid4().hex[:8]}"
    _active_tokens[token] = user_id
    return token


def verify_token(token: str) -> Optional[Dict[str, str]]:
    """Validate a token and return the associated user."""
    user_id = _active_tokens.get(token)
    if not user_id:
        return None
    return get_user_by_id(user_id)


def authenticate_user(username: str, password: str) -> Optional[Dict[str, str]]:
    """Verify demo username and password."""
    user = get_user_by_username(username)
    if not user:
        return None
    if user["password"] != password:
        return None
    return user


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
) -> Dict[str, str]:
    """Dependency to retrieve and authenticate the current user from Bearer header."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header. Please authenticate.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = verify_token(credentials.credentials)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def reset_auth() -> None:
    """Clear all active session tokens."""
    _active_tokens.clear()
