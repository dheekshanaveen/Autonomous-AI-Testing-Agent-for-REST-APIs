# Local Repository Testing Agent — project plan

## Goal

Give the tool a local project folder. It should understand how that project works, identify code paths likely to fail on unusual but valid or malformed inputs, generate focused regression tests, run them in isolation, and show exactly what failed. The result should help a developer reproduce and fix a real defect.

This is a resume project, so the showcase must work on unfamiliar projects and include measured results. The existing REST API prototype is a starting point for reusable ideas, not the scope of the new tool.

## First version

- Input: one local Python or JavaScript/TypeScript repository folder.
- Inspection: detect project structure, entry points, dependencies, existing tests, and documented behavior.
- Test ideas: derive boundary cases and unexpected input sequences from code, tests, types, and documentation. A free local model may suggest cases, but the core workflow must run without one.
- Execution: inspect the folder and run generated tests inside a disposable environment. Keep the source folder read-only and save outputs separately.
- Results: separate **Verified failures** (observed and reproduced) from **Leads to investigate** (plausible but unproven). Show the input, expected result, actual result, relevant source location, and runnable regression test.

## Build order

1. Build local-folder intake, project inventory, isolated runner, and an honest coverage report.
2. Generate and run one end-to-end test family for Python projects; verify that a generated test exposes a defect and passes after the defect is fixed.
3. Add JavaScript/TypeScript support and tests for stateful flows where the project provides the needed setup.
4. Evaluate on previously unseen projects. Record setup success, runnable tests, verified failures, false alarms, replay rate, and time per finding.

## Showcase standard

The demo uses at least two unfamiliar local repositories, including Python and JavaScript/TypeScript. For each reported failure, the generated test must reproduce it, then pass on a corrected version. The report must show what could not be tested. The tool must leave the selected source folder unchanged.

## Current boundary

The current workflow accepts local folders only. There is no organization account, cloud service, paid model requirement, or remote repository input. The tool cannot guarantee a defect in every project or call an untested path correct.
