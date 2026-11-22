# Empirical Benchmark & Tool Comparison Report

**Target System:** `http://127.0.0.1:8000`  
**Timestamp:** `2026-10-13T07:29:35.361838+00:00`  
**Evaluator:** Autonomous AI Testing Agent Benchmark Suite (Step 8)  

---

## 1. Executive Summary

This empirical benchmark compares our **Autonomous AI Testing Agent** against **Schemathesis (v4.31.0)**, an industry-standard property-based API fuzzer, running against the identical FastAPI sample shopping API.

Schemathesis excels at rapid fuzzing for 5xx server crashes and schema contract mismatches. However, Schemathesis cannot detect BOLA (OWASP API1:2023) because the vulnerable endpoint returns HTTP 200 OK with valid schema, requiring multi-user session management and object ownership oracles which only the Autonomous AI Testing Agent provides.

---

## 2. Comparative Metrics Table

| Evaluation Metric | Autonomous AI Testing Agent | Schemathesis (v4.31.0) | Note / Analysis |
| :--- | :---: | :---: | :--- |
| **Tool Paradigm** | Directed Graph Multi-Step Agent | Single-Request Property Fuzzer | Agent models dependent state sequences |
| **BOLA (OWASP API1) Detected** | **1 Found** | **0 Found** | Schemathesis missed BOLA; Agent caught it |
| **True Positives** | **1** | **0** | Confirmed genuine cross-user access flaw |
| **False Positives** | **0** | **0** | Zero false alarms recorded |
| **Total HTTP Requests** | 198 | 5 | Agent includes replays & delta debugging |
| **Total Elapsed Time** | 107.32s | 1.64s | Agent performs multi-run verification & minimization |
| **Test Minimization Ratio** | **60.0% (10 -> 4 reqs)** | **N/A (None)** | Agent isolates 1-minimal reproduction steps |
| **Flakiness / Replay Verification** | **Yes (100% reproducible)** | **No** | Clean database reset verification |
| **Root Cause Diagnosis** | **Yes (rule_based_fallback (no LLM API key configured))** | **No** | Explains missing object ownership check |
| **Suggested Code Fix** | **Yes (`order['user_id'] != current_user['user_id']`)** | **No** | Actionable remediation provided |
| **Standalone Pytest Reproduction** | **Yes (`reports/test_reproduce_bola.py`)** | **No** | Directly executable in CI/CD |
| **Estimated LLM Cost** | **$0.0000** | **$0.00** | Rule-based fallback operates at $0.00 cost |

---

## 3. Detailed Tool Analysis

### A. Autonomous AI Testing Agent Strengths
- **Stateful Sequence Orchestration:** Uses NetworkX directed graphs to link authentication tokens and dynamic resource IDs (`Login -> Create Order -> Cross-User Read`).
- **Multi-User Security Oracles:** Actively authenticates distinct security personas (`Alice` vs `Bob`) and asserts object ownership boundaries.
- **Automated Delta Debugging:** Eliminates redundant requests (e.g. intervening health pings) and extraneous JSON payload fields.
- **Actionable Developer Triage:** Delivers complete reproduction commands (`curl`, PowerShell, pytest) and code remediation recommendations.

### B. Schemathesis Strengths & Complementary Role
- **High-Throughput Schema Fuzzing:** Rapidly explores edge cases, extreme string lengths, boundary integers, and regex patterns against OpenAPI schemas.
- **5xx Crash Detection:** Highly effective at uncovering unhandled exceptions, null dereferences, and deserialization crashes.
- **Zero-Configuration Setup:** Automatically loads OpenAPI schemas directly from URL or JSON file without writing custom test plans.

### C. Why Schemathesis Missed the BOLA Vulnerability
1. **Independent Request Execution:** Schemathesis executes endpoints independently rather than orchestrating stateful cross-user sessions.
2. **Schema Conformance Concealment:** The vulnerable `GET /orders/{order_id}` endpoint returns HTTP 200 OK with a valid `OrderResponse` body. Because the response schema matches the OpenAPI contract, standard schema fuzzers evaluate the test as *passed*.
3. **Lack of Identity Context:** Schemathesis does not know that Bob is accessing an object created by Alice without custom security oracles.

---

## 4. Threats to Validity & Limitations

- **Single Benchmark Target:** Results are evaluated against our controlled sample shopping API. Real-world microservices may have more complex authentication topologies (e.g. OAuth2 authorization code grants, SAML).
- **Known Vulnerability Bias:** The BOLA vulnerability was intentionally introduced. While the agent did not hardcode the endpoint and discovered it via its oracle, additional evaluation on external open-source APIs is warranted in future work.
- **Minimization Execution Overhead:** Delta debugging requires multiple candidate replays with clean state resets, which increases total testing time on slower APIs.

---

## 5. Reproduction Instructions

To repeat this benchmark experiment independently:

```powershell
# 1. Start the Sample API
python -m uvicorn sample_api.main:app --host 127.0.0.1 --port 8000

# 2. Run the Benchmark Evaluator
python -m benchmarks.evaluator http://127.0.0.1:8000

# 3. Inspect Generated Outputs
Get-Content benchmarks/BENCHMARK_REPORT.md
```