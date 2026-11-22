"""Runner module: executes tests inside an isolated environment with bounded resources."""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional
from local_agent.models import ExecutionResult


class IsolatedRunner:
    """Runs generated tests with bounded resources and isolated environment."""

    def __init__(self, timeout_seconds: float = 5.0, python_executable: Optional[str] = None):
        self.timeout_seconds = timeout_seconds
        # Resolve python executable: prefer current virtualenv python if present
        if python_executable:
            self.python_executable = python_executable
        else:
            venv_python = Path(sys.prefix) / "Scripts" / "python.exe"
            if venv_python.exists():
                self.python_executable = str(venv_python)
            else:
                self.python_executable = sys.executable

        self.node_executable = shutil.which("node") or "node"

    def run_test(
        self, test_file: Path, language: str, repo_root: Path
    ) -> ExecutionResult:
        """Run a test file in isolation with bounded timeout."""
        test_file = Path(test_file).resolve()
        repo_root = Path(repo_root).resolve()

        with tempfile.TemporaryDirectory(prefix="agent_run_") as temp_dir:
            temp_path = Path(temp_dir)
            start_time = time.perf_counter()

            if language == "python":
                cmd = [
                    self.python_executable,
                    "-m",
                    "pytest",
                    str(test_file),
                    "-v",
                    "--tb=short",
                    "--no-header",
                ]
                env = os.environ.copy()
                env["PYTHONPATH"] = str(repo_root.resolve())
                env["REPO_ROOT"] = str(repo_root.resolve())
                env["PYTHONDONTWRITEBYTECODE"] = "1"
            else:
                # JavaScript / TypeScript via Node's native test runner
                cmd = [self.node_executable, "--test", str(test_file)]
                env = os.environ.copy()
                env["NODE_PATH"] = str(repo_root.resolve())
                env["REPO_ROOT"] = str(repo_root.resolve())

            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(temp_path),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=self.timeout_seconds,
                    encoding="utf-8",
                    errors="replace",
                )
                duration = time.perf_counter() - start_time
                stdout = proc.stdout
                stderr = proc.stderr
                exit_code = proc.returncode
                passed = (exit_code == 0)
                timed_out = False

            except subprocess.TimeoutExpired as te:
                duration = time.perf_counter() - start_time
                stdout = (te.stdout or "") if isinstance(te.stdout, str) else ""
                stderr = (te.stderr or "") if isinstance(te.stderr, str) else ""
                exit_code = -1
                passed = False
                timed_out = True

            failure_type, error_msg = self._extract_error_details(
                stdout, stderr, language, timed_out
            )

            return ExecutionResult(
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=round(duration, 3),
                timed_out=timed_out,
                passed=passed,
                error_message=error_msg,
                failure_type=failure_type,
            )

    @staticmethod
    def _extract_error_details(
        stdout: str, stderr: str, language: str, timed_out: bool
    ) -> tuple[Optional[str], Optional[str]]:
        if timed_out:
            return "TimeoutError", "Execution timed out (resource limit exceeded or infinite loop)"

        combined = f"{stdout}\n{stderr}"

        # Setup gap detection: missing packages / external modules
        if "ModuleNotFoundError:" in combined:
            m = re.search(r"ModuleNotFoundError:\s*(.*)", combined)
            return "SetupGap:ModuleNotFound", m.group(1).strip() if m else "Missing module"
        if "Cannot find module" in combined or "ERR_MODULE_NOT_FOUND" in combined:
            m = re.search(r"Cannot find module\s+'([^']+)'", combined)
            return "SetupGap:ModuleNotFound", m.group(1).strip() if m else "Missing npm package"

        if language == "python":
            # Match python traceback last exception line
            # e.g., "E   ZeroDivisionError: division by zero" or "ZeroDivisionError: division by zero"
            m = re.search(r"(?:E\s+)?([A-Z][A-Za-z0-9_]*Error|[A-Z][A-Za-z0-9_]*Exception):\s*(.*)", combined)
            if m:
                return m.group(1).strip(), m.group(2).strip()
            # Pytest assertion failure: "assert 1 == 2" or "AssertionError"
            if "AssertionError" in combined or re.search(r"(?:E\s+)?assert\s+", combined):
                return "AssertionError", "Assertion failed"

        else:
            # JavaScript errors
            # e.g., "TypeError: Cannot read properties of undefined"
            m = re.search(r"([A-Z][A-Za-z0-9_]*Error):\s*(.*)", combined)
            if m:
                return m.group(1).strip(), m.group(2).strip()

        if "FAIL" in combined or "failed" in combined.lower():
            return "Failure", "Test failed"

        return None, None

