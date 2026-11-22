"""Tests for CLI interface."""

import subprocess
import sys
from pathlib import Path


def test_cli_help():
    result = subprocess.run(
        [sys.executable, "-m", "local_agent", "--help"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert result.returncode == 0
    assert "Local Repository Testing Agent" in result.stdout


def test_cli_inventory(sample_python_repo_path):
    result = subprocess.run(
        [sys.executable, "-m", "local_agent", "inventory", str(sample_python_repo_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert result.returncode == 0
    assert "stream_metrics" in result.stdout
    assert "compute_moving_average" in result.stdout


def test_cli_scan_valid(sample_python_repo_path, temp_dir):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "local_agent",
            "scan",
            str(sample_python_repo_path),
            "--output",
            str(temp_dir),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert result.returncode == 0
    assert "SCAN SUMMARY" in result.stdout
    assert "Folder untouched:         YES" in result.stdout


def test_cli_invalid_path():
    result = subprocess.run(
        [sys.executable, "-m", "local_agent", "scan", "C:/invalid_nonexistent_path_xyz"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert result.returncode == 2
    assert "Error:" in result.stderr

