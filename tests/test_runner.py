"""Tests for isolated runner module."""

from pathlib import Path
from local_agent.runner import IsolatedRunner


def test_runner_passing_test(temp_dir):
    test_code = """
def test_passing():
    assert 1 + 1 == 2
"""
    test_file = temp_dir / "test_pass.py"
    test_file.write_text(test_code, encoding="utf-8")

    runner = IsolatedRunner(timeout_seconds=5.0)
    result = runner.run_test(test_file, "python", temp_dir)

    assert result.passed is True
    assert result.exit_code == 0
    assert result.timed_out is False


def test_runner_failing_test(temp_dir):
    test_code = """
def test_failing():
    assert 1 == 2
"""
    test_file = temp_dir / "test_fail.py"
    test_file.write_text(test_code, encoding="utf-8")

    runner = IsolatedRunner(timeout_seconds=5.0)
    result = runner.run_test(test_file, "python", temp_dir)

    assert result.passed is False
    assert result.exit_code != 0
    assert result.failure_type == "AssertionError"


def test_runner_timeout_bounded(temp_dir):
    test_code = """
import time
def test_infinite_loop():
    while True:
        time.sleep(0.1)
"""
    test_file = temp_dir / "test_timeout.py"
    test_file.write_text(test_code, encoding="utf-8")

    # Short timeout of 1.0 second
    runner = IsolatedRunner(timeout_seconds=1.0)
    result = runner.run_test(test_file, "python", temp_dir)

    assert result.passed is False
    assert result.timed_out is True
    assert result.failure_type == "TimeoutError"


def test_runner_setup_gap_detection(temp_dir):
    test_code = """
def test_missing_module():
    import nonexistent_random_package_12345
"""
    test_file = temp_dir / "test_missing.py"
    test_file.write_text(test_code, encoding="utf-8")

    runner = IsolatedRunner(timeout_seconds=5.0)
    result = runner.run_test(test_file, "python", temp_dir)

    assert result.passed is False
    assert result.failure_type == "SetupGap:ModuleNotFound"

