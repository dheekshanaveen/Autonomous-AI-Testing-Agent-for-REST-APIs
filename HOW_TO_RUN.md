# How to Run the Local Repository Testing Agent

This guide provides step-by-step instructions for setting up the environment, scanning local repositories, replaying regression tests, running benchmarks, and executing the test suite.

---

## 1. Prerequisites

Ensure your system has the following installed:

- **Python 3.10+** (tested on Python 3.10 through 3.14)
- **Node.js 18+** (required for scanning JavaScript/TypeScript projects using the native `node:test` runner; no third-party npm packages required)
- **Git**

---

## 2. Environment Setup

### On Windows (PowerShell)

```powershell
# 1. Clone or navigate to the repository directory
cd "path\to\mini_project"

# 2. Create a virtual environment
python -m venv venv

# 3. Activate the virtual environment
.\venv\Scripts\Activate.ps1

# 4. Install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> **Note for Windows users:** If script execution is disabled in PowerShell, enable it for your current session by running:
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
> ```

### On Linux / macOS (Bash / Zsh)

```bash
# 1. Navigate to the repository directory
cd path/to/mini_project

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 3. CLI Commands Overview

The testing agent is invoked as a Python module:

```powershell
python -m local_agent <command> [options]
```

Available subcommands:
- `scan`: Analyzes a local repository, generates candidate regression tests, executes them in isolation, replays failures, and writes detailed reports.
- `inventory`: Inspects and displays the repository's structure, entry points, detected languages, manifests, and AST-parsed code symbols without running tests.
- `replay`: Re-runs a specific generated regression test against a target repository.

---

## 4. Running a Project Scan (`scan`)

### Basic Scan

To scan a local repository:

```powershell
python -m local_agent scan path/to/target_repository
```

### Example: Scanning the Python Benchmark Repository

```powershell
python -m local_agent scan benchmarks/sample_python_repo
```

### Scan Options

| Option | Flag | Description | Default |
| :--- | :--- | :--- | :--- |
| **Output Directory** | `--output`, `-o` | Directory where generated tests and reports will be saved | `<parent>/scan_output_<repo_name>` |
| **Test Timeout** | `--timeout`, `-t` | Per-test execution time limit in seconds | `5.0` |
| **Cross-Revision Fix Verification** | `--verify-fix` | Path to a corrected revision of the repository | `None` |

### Example with Custom Output and Timeout

```powershell
python -m local_agent scan benchmarks/sample_python_repo --output scan_reports/python_run --timeout 10.0
```

### Example with Fix Verification (`--verify-fix`)

This feature proves that generated tests reproduce the bugs on the faulty code and pass cleanly on the corrected code:

```powershell
python -m local_agent scan benchmarks/sample_python_repo --verify-fix benchmarks/sample_python_repo_fixed
```

### Example: Scanning a JavaScript Project

```powershell
python -m local_agent scan benchmarks/sample_js_repo --verify-fix benchmarks/sample_js_repo_fixed
```

---

## 5. Inspecting Project Inventory (`inventory`)

If you want to view project manifests, detected languages, and AST-extracted functions/classes without executing any tests:

```powershell
python -m local_agent inventory benchmarks/sample_python_repo
```

Output includes:
- Target language(s) (Python, JavaScript, TypeScript)
- Project manifests (`pyproject.toml`, `package.json`, etc.)
- Discovered source files
- Code symbols, parameters, return types, docstring contracts, and AST risk flags (such as division by zero, unhandled null dereferences, and empty sequence risks).

---

## 6. Replaying a Generated Test (`replay`)

Every verified finding includes an exact replay command. You can replay any test directly:

### For Python (`pytest`):

```powershell
python -m local_agent replay <path_to_test_file.py> <path_to_repository> --language python
```

Or invoke `pytest` directly:

```powershell
pytest <path_to_test_file.py> -v
```

### For JavaScript (`node --test`):

```powershell
python -m local_agent replay <path_to_test_file.test.mjs> <path_to_repository> --language javascript
```

Or invoke Node's test runner directly:

```powershell
node --test <path_to_test_file.test.mjs>
```

---

## 7. Running the Automated Showcase & Benchmark Evaluator

The repository includes an empirical benchmark suite evaluating Python, JavaScript, and Unsupported projects side-by-side:

```powershell
python -m benchmarks.evaluator
```

This runs:
1. **Python Stream Metrics:** Unfamiliar project with zero-division, empty list indexing, and contract violation defects.
2. **JavaScript Token Matrix:** Unfamiliar project with null dereference, contract violations, and buffer underflow.
3. **Unsupported Cloud Service:** Project with missing external dependencies to verify honest setup gap reporting.
4. **Fix Verification:** Verifies fixes against the `*_fixed` repositories.
5. **Folder Immutability Check:** Confirms that all source repositories remained 100% untouched.

Outputs produced:
- Markdown Report: [benchmarks/BENCHMARK_REPORT.md](benchmarks/BENCHMARK_REPORT.md)
- JSON Data: [benchmarks/benchmark_results.json](benchmarks/benchmark_results.json)
- Tabular CSV: [benchmarks/benchmark_results.csv](benchmarks/benchmark_results.csv)

---

## 8. Running the Automated Test Suite

Run all 26 unit and end-to-end integration tests using `pytest`:

```powershell
pytest -v
```

To run individual test modules:

```powershell
# Test repository intake and immutability checks
pytest tests/test_intake.py -v

# Test AST inspection and contract parsing
pytest tests/test_inventory.py -v

# Test candidate generation logic
pytest tests/test_analyzer.py -v

# Test test code generation (pytest and node:test)
pytest tests/test_generator.py -v

# Test isolated runner and timeouts
pytest tests/test_runner.py -v

# Test two-phase replay verifier and fix verification
pytest tests/test_verifier.py -v

# Test report generation
pytest tests/test_reporter.py -v

# Test CLI commands
pytest tests/test_cli.py -v

# Test end-to-end benchmark showcase and acceptance criteria
pytest tests/test_benchmarks_e2e.py -v
```

---

## 9. Understanding the Scan Reports

When a scan finishes, the output directory contains:

- `scan_report.md`: Human-readable Markdown summary with metrics, verified defects, execution evidence, and reproduction commands.
- `scan_report.json`: Machine-readable structured result conforming to Pydantic data schemas.
- `generated_tests/`: Runnable test files (`test_regress_*.py` or `test_regress_*.test.mjs`).

### Classification Definitions

- **Verified Failure:** The generated test failed on run 1 AND an independent replay run reproduced the exact same failure. Includes source line reference, exact inputs, observed failure, and replay instructions.
- **Lead to Investigate:** Plausible defect idea or non-reproducible test observation where failure could not be confirmed upon replay.
- **Setup Gap:** Execution could not be completed due to missing dependencies, unfulfilled external network requirements, or syntax constraints. Honestly reported without triggering false alarms.
- **Source Folder Integrity:** Explicit SHA-256 confirmation proving the scanned project folder was never modified.
