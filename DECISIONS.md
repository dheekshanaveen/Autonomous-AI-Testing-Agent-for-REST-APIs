# Current project decisions

This file records choices for the active project. Update it when a choice changes or an implementation decision is made. The earlier REST API prototype decisions remain available in Git history.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-16 | Build a local repository testing agent. | The user wants to give the tool an unfamiliar project and see a concrete failing input with a test. |
| 2026-11-16 | Use local folder paths for input. | This is the current development and demonstration workflow. |
| 2026-11-16 | Support Python and JavaScript/TypeScript first. | These provide two useful ecosystems with a bounded initial scope. |
| 2026-11-16 | Run inspection and tests in an isolated environment; leave the selected source folder unchanged. | Generated tests and project commands must not affect the developer's working copy. |
| 2026-11-16 | Distinguish verified failures from leads. | A code pattern or model suggestion is not evidence of a runtime failure. |
| 2026-11-16 | Require no paid model or organization service. | The project should be practical for a student and easy to demonstrate locally. |
| 2026-11-16 | Use the existing REST API code as a prototype, not as the new product boundary. | The new workflow needs to work on unfamiliar repositories. |
| 2026-11-16 | Modularize into `local_agent` core package (`intake`, `inventory`, `analyzer`, `generator`, `runner`, `verifier`, `reporter`, `cli`). | Clean architectural separation of responsibilities matching the routing diagram. |
| 2026-11-16 | Implement strict two-phase deterministic replay for verification. | Eliminates false alarms and flaky test hypotheses; only reproduced failures become findings. |
| 2026-11-16 | Native `node:test` runner for JS/TS and `pytest` for Python. | Guarantees self-contained execution without external npm dependencies. |
| 2026-11-16 | SHA-256 pre- and post-scan directory integrity manifest checks. | Guarantees and proves the selected local folder is never modified. |
| 2026-11-16 | Cross-revision fix verification (`verify-fix`). | Verifies that generated tests fail on faulty versions and pass when corrected. |
| 2026-11-16 | Archive legacy REST API prototype into `legacy_rest_prototype/`. | Cleans up workspace root and ensures tests focus entirely on the local testing agent. |

Implementation choices and changed decisions should be appended here with a date and the reason.
