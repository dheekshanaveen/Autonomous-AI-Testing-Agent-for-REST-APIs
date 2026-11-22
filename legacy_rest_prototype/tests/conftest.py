"""Pytest configuration and shared fixtures."""

import pytest
from fastapi.testclient import TestClient

from sample_api.main import app
from sample_api.database import reset_db
from sample_api.auth import reset_auth


@pytest.fixture(autouse=True)
def clean_database():
    """Ensure every test runs against a clean, isolated database and session state."""
    reset_db()
    reset_auth()
    yield
    reset_db()
    reset_auth()


@pytest.fixture
def client():
    """FastAPI test client fixture."""
    return TestClient(app)
