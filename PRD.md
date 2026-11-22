# Product requirements: Local Repository Testing Agent

## Problem and user

A student or developer can inherit an unfamiliar project and spend a long time finding meaningful edge cases. Existing tests often cover examples that already work. This tool helps turn project understanding into small, reproducible tests for behavior that may fail.

## Product outcome

Select a local repository folder and receive a report with runnable tests. A finding is **verified** only when the generated test observes the failure and a repeat run reproduces it. Other observations remain **leads** with a reason they could not be confirmed.

## Requirements

1. Accept a local folder path and reject missing, unreadable, or unsupported input with a useful explanation. Never alter the selected source folder.
2. Inspect Python and JavaScript/TypeScript projects for structure, entry points, tests, input handling, and expected behavior expressed in code or documentation.
3. Generate focused tests for boundary values, malformed input, state transitions, and documented contracts where the project supplies enough context.
4. Perform inspection, test generation, execution, and replay in an isolated environment with bounded resources. Write generated tests and reports outside the selected folder.
5. Report exact inputs, expected and observed behavior, source references, execution evidence, and replay instructions. Keep verified failures separate from unverified leads and setup gaps.
6. Work without a paid AI service. A free local model may help prioritize test ideas; its suggestions require execution before becoming findings.

## Acceptance criteria

- A clean scan leaves the selected folder unchanged.
- A generated test fails on a known faulty revision and passes on its corrected revision.
- The report does not mark a suggestion as verified when setup, execution, or replay fails.
- The showcase covers unfamiliar Python and JavaScript/TypeScript projects and publishes the measured results, including unsuccessful setups.

## Current state

The repository contains an earlier REST API testing prototype. The local repository workflow described here is the next build, not a feature already completed. See [PROJECT_PLAN.md](PROJECT_PLAN.md) for build order, [DECISIONS.md](DECISIONS.md) for chosen directions, [ASSUMPTIONS.md](ASSUMPTIONS.md) for working assumptions, and [ROUTING.md](ROUTING.md) for the component flow.
