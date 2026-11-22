# Showcase Evaluation & Empirical Benchmark Report

## Overview

This report publishes empirical evaluation results of the **Local Repository Testing Agent** across unfamiliar Python and JavaScript/TypeScript projects, including clean and unsuccessful setups.

- **Evaluation Timestamp:** `2026-11-16T11:19:55Z`
- **Total Duration:** `44.5s`
- **Total Targets Evaluated:** `3`
- **Total Verified Failures:** `14`
- **False Alarms:** `0` (0.0% False Positive Rate)
- **Source Folder Immutability:** `100% Untouched (Verified)`

---

## Summary Metrics Table

| Repository Target | Language | Setup Success | Runnable Tests | Verified Failures | Leads | Setup Gaps | False Alarms | Replay Rate | Scan Duration | Folder Untouched | Fixes Confirmed |
| --- | --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Python Stream Metrics (Faulty)** | python | ✅ Yes | 22 | **11** | 0 | 0 | 0 | 100.0% | 14.63s | ✅ Yes | ✅ Yes (All) |
| **JavaScript Token Matrix (Faulty)** | javascript | ✅ Yes | 13 | **3** | 0 | 0 | 0 | 100.0% | 1.76s | ✅ Yes | ✅ Yes (All) |
| **Unsupported Cloud Service (Missing Dependency)** | python | ⚠️ Gap Reported | 5 | **0** | 0 | 5 | 0 | 100.0% | 2.25s | ✅ Yes | N/A |

---

## Target Project Evaluations

### Python Stream Metrics (Faulty)

- **Repository Path:** `C:\Users\Shashi kiran\Grinding\mini_project\benchmarks\sample_python_repo`
- **Language:** python
- **Files Scanned:** 4 | **Symbols Analyzed:** 7
- **Candidates Generated:** 22 | **Tests Run:** 22
- **Verified Failures:** 11 | **Leads:** 0 | **Setup Gaps:** 0
- **Folder Untouched:** ✅ Verified SHA-256 integrity match

#### Verified Defects:
- **`compute_moving_average`** (`ast_heuristic`): ZeroDivisionError: division by zero
  - Replay: `pytest C:/Users/Shashi kiran/Grinding/mini_project/reports/evaluation_artifacts/sample_python_repo/generated_tests/test_regress_compute_moving_average_cand-61f37648.py -v`
- **`compute_moving_average`** (`boundary_value`): ZeroDivisionError: division by zero
  - Replay: `pytest C:/Users/Shashi kiran/Grinding/mini_project/reports/evaluation_artifacts/sample_python_repo/generated_tests/test_regress_compute_moving_average_cand-0a344d2f.py -v`
- **`compute_moving_average`** (`boundary_value`): ZeroDivisionError: division by zero
  - Replay: `pytest C:/Users/Shashi kiran/Grinding/mini_project/reports/evaluation_artifacts/sample_python_repo/generated_tests/test_regress_compute_moving_average_cand-68faf498.py -v`
- **`calculate_ratio`** (`ast_heuristic`): ZeroDivisionError: division by zero
  - Replay: `pytest C:/Users/Shashi kiran/Grinding/mini_project/reports/evaluation_artifacts/sample_python_repo/generated_tests/test_regress_calculate_ratio_cand-d2c38fa8.py -v`
- **`calculate_ratio`** (`contract_violation`): AssertionError: Expected documented exception was not raised
  - Replay: `pytest C:/Users/Shashi kiran/Grinding/mini_project/reports/evaluation_artifacts/sample_python_repo/generated_tests/test_regress_calculate_ratio_cand-088f57e8.py -v`
- **`calculate_ratio`** (`boundary_value`): ZeroDivisionError: division by zero
  - Replay: `pytest C:/Users/Shashi kiran/Grinding/mini_project/reports/evaluation_artifacts/sample_python_repo/generated_tests/test_regress_calculate_ratio_cand-483bbdbe.py -v`
- **`calculate_ratio`** (`boundary_value`): ZeroDivisionError: division by zero
  - Replay: `pytest C:/Users/Shashi kiran/Grinding/mini_project/reports/evaluation_artifacts/sample_python_repo/generated_tests/test_regress_calculate_ratio_cand-cd9eeef1.py -v`
- **`transform_records`** (`boundary_value`): IndexError: list index out of range
  - Replay: `pytest C:/Users/Shashi kiran/Grinding/mini_project/reports/evaluation_artifacts/sample_python_repo/generated_tests/test_regress_transform_records_cand-215c3983.py -v`
- **`transform_records`** (`boundary_value`): IndexError: list index out of range
  - Replay: `pytest C:/Users/Shashi kiran/Grinding/mini_project/reports/evaluation_artifacts/sample_python_repo/generated_tests/test_regress_transform_records_cand-0e92014e.py -v`
- **`StreamSession`** (`state_transition`): IndexError: pop from empty list
  - Replay: `pytest C:/Users/Shashi kiran/Grinding/mini_project/reports/evaluation_artifacts/sample_python_repo/generated_tests/test_regress_StreamSession_cand-aca031ba.py -v`
- **`StreamSession`** (`state_transition`): IndexError: pop from empty list
  - Replay: `pytest C:/Users/Shashi kiran/Grinding/mini_project/reports/evaluation_artifacts/sample_python_repo/generated_tests/test_regress_StreamSession_cand-38678bcd.py -v`

### JavaScript Token Matrix (Faulty)

- **Repository Path:** `C:\Users\Shashi kiran\Grinding\mini_project\benchmarks\sample_js_repo`
- **Language:** javascript
- **Files Scanned:** 2 | **Symbols Analyzed:** 3
- **Candidates Generated:** 13 | **Tests Run:** 13
- **Verified Failures:** 3 | **Leads:** 0 | **Setup Gaps:** 0
- **Folder Untouched:** ✅ Verified SHA-256 integrity match

#### Verified Defects:
- **`extractTokens`** (`malformed_input`): TypeError: Cannot read properties of null (reading 'split')
  - Replay: `node --test C:/Users/Shashi kiran/Grinding/mini_project/reports/evaluation_artifacts/sample_js_repo/generated_tests/test_regress_extractTokens_cand-3fd94971.test.mjs`
- **`extractTokens`** (`malformed_input`): TypeError: Cannot read properties of null (reading 'split')
  - Replay: `node --test C:/Users/Shashi kiran/Grinding/mini_project/reports/evaluation_artifacts/sample_js_repo/generated_tests/test_regress_extractTokens_cand-c482a29c.test.mjs`
- **`normalizeWeight`** (`contract_violation`): Test failed
  - Replay: `node --test C:/Users/Shashi kiran/Grinding/mini_project/reports/evaluation_artifacts/sample_js_repo/generated_tests/test_regress_normalizeWeight_cand-e81cb955.test.mjs`

### Unsupported Cloud Service (Missing Dependency)

- **Repository Path:** `C:\Users\Shashi kiran\Grinding\mini_project\benchmarks\sample_unsupported_repo`
- **Language:** python
- **Files Scanned:** 2 | **Symbols Analyzed:** 1
- **Candidates Generated:** 5 | **Tests Run:** 5
- **Verified Failures:** 0 | **Leads:** 0 | **Setup Gaps:** 5
- **Folder Untouched:** ✅ Verified SHA-256 integrity match

---

## Acceptance Criteria Compliance

1. **Clean scan leaves selected folder unchanged:**
   - Verified: All target repositories were checksummed before and after scanning. Zero modifications, additions, or deletions occurred.
2. **Generated test fails on known faulty revision and passes on corrected revision:**
   - Verified: Tests generated against faulty Python and JavaScript revisions reproduced defects and passed cleanly on the corrected revisions.
3. **Report does not mark suggestion as verified when setup, execution, or replay fails:**
   - Verified: In `Unsupported Cloud Service`, missing dependencies were honestly classified as `SETUP_GAP`, with 0 unverified suggestions marked as verified.
4. **Showcase covers unfamiliar Python and JavaScript/TypeScript projects with published measurements:**
   - Verified: Metrics published in this report, `benchmark_results.json`, and `benchmark_results.csv`.
