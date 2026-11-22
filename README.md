# Local Repository Testing Agent

An autonomous, deterministic agent that inspects a **local repository folder**, derives edge cases and unexpected input sequences, generates focused standalone regression tests, executes and replays them in an isolated environment, and delivers honest reports distinguishing verified failures from unverified leads and setup gaps.

Supported language ecosystems: **Python** and **JavaScript/TypeScript**.

---

## Key Highlights & Guarantees

1. **Strict Folder Immutability:** Pre- and post-scan SHA-256 integrity verification guarantees the target repository remains 100% untouched. All generated tests and reports are written to separate output directories.
2. **Two-Phase Deterministic Replay:** A finding is classified as a **Verified Failure** only if the generated test observes a failure on run 1 AND an independent replay run confirms and reproduces it. Flaky failures remain **Leads**.
3. **Honest Reporting:** Zero false alarms. Missing external dependencies or network services are reported as **Setup Gaps** rather than spurious bugs.
4. **Fix Verification:** Built-in cross-revision verification (`--verify-fix`) proves that generated regression tests fail on buggy code and pass on corrected code.
5. **Completely Local & Zero Cost:** Works deterministically without requiring paid AI services or external SaaS accounts.

---

## Repository Documentation

- [How to Run](HOW_TO_RUN.md) — Step-by-step setup and execution guide.
- [Project Plan](PROJECT_PLAN.md) — Goal, build order, and showcase standards.
- [Product Requirements (PRD)](PRD.md) — Problem statement, requirements, and acceptance criteria.
- [Component Routing](ROUTING.md) — Architectural pipeline flow from intake to reporting.
- [Decisions](DECISIONS.md) — Architectural decision log.
- [Assumptions](ASSUMPTIONS.md) — Working assumptions and empirical checks.
- [Benchmark Report](benchmarks/BENCHMARK_REPORT.md) — Empirical showcase evaluation results.

---

## Architecture Pipeline

```
[Local Folder Intake]
        │ (Validates path, enforces read-only immutability)
        ▼
[Project Inventory]
        │ (Scans manifests, AST, docstrings, type hints, test suites)
        ▼
[Candidate Analysis]
        │ (Derives boundary values, malformed inputs, state transitions, contracts)
        ▼
[Test Generator]
        │ (Generates standalone pytest or node:test regression files outside repo)
        ▼
[Isolated Runner]
        │ (Executes in sandboxed subprocess with strict resource/timeout bounding)
        ▼
[Replay & Classifier]
        │ (Two-phase replay verification: verified failure vs lead vs setup gap)
        ▼
[Report Writer]
        │ (Produces markdown, JSON, and reproduction CLI commands)
        ▼
      [User]
```

---

## Installation & Setup

### Prerequisites

- Python 3.10+
- Node.js 18+ (for JavaScript/TypeScript scanning using native `node:test`)

### Quick Setup

```powershell
# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install requirements
pip install -r requirements.txt
```

---

## Usage Guide

### 1. Scan a Local Repository

Scan a target repository, run isolated tests, and produce structured reports:

```powershell
python -m local_agent scan path/to/local_repository
```

Options:
- `--output, -o <dir>`: Custom directory for reports and generated regression tests.
- `--timeout, -t <seconds>`: Per-test execution timeout limit in seconds (default: 5.0).
- `--verify-fix <fixed_repo_path>`: Cross-verify that generated tests fail on the target repo and pass on a corrected revision.

### 2. Inspect Project Inventory

View detected languages, manifests, source files, and code symbols:

```powershell
python -m local_agent inventory path/to/local_repository
```

### 3. Replay a Generated Regression Test

Replay any generated test against a repository in isolation:

```powershell
python -m local_agent replay path/to/generated_test.py path/to/local_repository
```

---

## Empirical Benchmark & Showcase

Run the showcase evaluation across Python, JavaScript, and Unsupported benchmark projects:

```powershell
python -m benchmarks.evaluator
```

Benchmark targets:
- `benchmarks/sample_python_repo`: Unfamiliar Python streaming engine with division-by-zero, empty collection underflow, and contract defects.
- `benchmarks/sample_python_repo_fixed`: Corrected Python revision.
- `benchmarks/sample_js_repo`: Unfamiliar JavaScript token processor with null dereference, contract violation, and state machine underflow.
- `benchmarks/sample_js_repo_fixed`: Corrected JavaScript revision.
- `benchmarks/sample_unsupported_repo`: Project with missing native drivers to evaluate honest setup gap reporting.

Results are published to:
- `benchmarks/BENCHMARK_REPORT.md`
- `benchmarks/benchmark_results.json`
- `benchmarks/benchmark_results.csv`

---

## Running Automated Tests

Run the full automated test suite (26 unit and integration tests):

```powershell
pytest -v
```
