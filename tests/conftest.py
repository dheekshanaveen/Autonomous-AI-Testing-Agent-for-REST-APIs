"""Pytest fixtures for testing agent."""

import shutil
import tempfile
from pathlib import Path
import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory cleaned up after test."""
    temp_path = Path(tempfile.mkdtemp(prefix="agent_test_"))
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def sample_python_repo_path():
    """Path to sample python benchmark repository."""
    return Path(__file__).resolve().parent.parent / "benchmarks" / "sample_python_repo"


@pytest.fixture
def sample_python_fixed_path():
    """Path to sample python fixed repository."""
    return Path(__file__).resolve().parent.parent / "benchmarks" / "sample_python_repo_fixed"


@pytest.fixture
def sample_js_repo_path():
    """Path to sample javascript benchmark repository."""
    return Path(__file__).resolve().parent.parent / "benchmarks" / "sample_js_repo"


@pytest.fixture
def sample_js_fixed_path():
    """Path to sample javascript fixed repository."""
    return Path(__file__).resolve().parent.parent / "benchmarks" / "sample_js_repo_fixed"


@pytest.fixture
def sample_unsupported_repo_path():
    """Path to sample unsupported repository."""
    return Path(__file__).resolve().parent.parent / "benchmarks" / "sample_unsupported_repo"

