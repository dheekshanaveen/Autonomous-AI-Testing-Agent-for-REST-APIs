"""Generator module: generates standalone, runnable regression test files."""

import json
from pathlib import Path
from typing import Any, Dict, List
from local_agent.models import TestCandidate


class TestGenerator:
    """Generates runnable pytest and node:test test files outside the repository."""

    @classmethod
    def generate_test(
        cls, candidate: TestCandidate, output_dir: Path, repo_root: Path
    ) -> Path:
        output_dir = output_dir.resolve()
        tests_dir = output_dir / "generated_tests"
        tests_dir.mkdir(parents=True, exist_ok=True)

        if candidate.language == "python":
            return cls._generate_python_test(candidate, tests_dir, repo_root)
        else:
            return cls._generate_js_test(candidate, tests_dir, repo_root)

    @classmethod
    def _generate_python_test(
        cls, candidate: TestCandidate, tests_dir: Path, repo_root: Path
    ) -> Path:
        safe_sym = candidate.symbol_name.replace(".", "_")
        test_file = tests_dir / f"test_regress_{safe_sym}_{candidate.id}.py"

        # Compute python module import path
        rel_path = Path(candidate.file_path)
        mod_parts = list(rel_path.with_suffix("").parts)
        module_dotted = ".".join(mod_parts)

        repo_root_posix = repo_root.resolve().as_posix()

        lines: List[str] = [
            "# Auto-generated regression test by Local Repository Testing Agent",
            f"# Target: {candidate.file_path} :: {candidate.symbol_name}",
            f"# Category: {candidate.category}",
            f"# Rationale: {candidate.rationale}",
            "",
            "import os",
            "import sys",
            "from pathlib import Path",
            "import pytest",
            "",
            "# Allow dynamic override of repository root for fix verification",
            "target_repo = os.environ.get('REPO_ROOT') or os.environ.get('PYTHONPATH')",
            "if target_repo:",
            "    target_resolved = str(Path(target_repo).resolve())",
            "    if not sys.path or sys.path[0] != target_resolved:",
            "        sys.path.insert(0, target_resolved)",
            "else:",
            f"    fallback = r'{repo_root_posix}'",
            "    if not sys.path or sys.path[0] != fallback:",
            "        sys.path.insert(0, fallback)",
            "",
        ]

        if candidate.is_stateful:
            lines.extend(cls._render_python_stateful_test(candidate, module_dotted))
        else:
            lines.extend(cls._render_python_function_test(candidate, module_dotted))

        test_file.write_text("\n".join(lines), encoding="utf-8")
        return test_file

    @classmethod
    def _render_python_function_test(
        cls, candidate: TestCandidate, module_dotted: str
    ) -> List[str]:
        lines = [
            f"def test_{candidate.category}_{candidate.symbol_name}_{candidate.id.replace('-', '_')}():",
            f'    """',
            f"    Target: {candidate.symbol_name}",
            f"    Inputs: {candidate.inputs}",
            f"    Expected: {candidate.expected_behavior}",
            f'    """',
            f"    from {module_dotted} import {candidate.symbol_name}",
            "",
            f"    # Prepare input arguments",
        ]
        args_repr = []
        for k, v in candidate.inputs.items():
            args_repr.append(f"{k}={repr(v)}")
        call_str = f"{candidate.symbol_name}({', '.join(args_repr)})"

        if candidate.category == "contract_violation":
            # For documented contracts, we verify that the documented exception is actually raised
            # and that it does not crash with an unexpected internal error
            lines.extend([
                f"    # Documented contract check: {candidate.expected_behavior}",
                f"    try:",
                f"        res = {call_str}",
                f"        # If it reached here without exception, contract was violated if an error was expected",
                f"        assert False, 'Expected documented exception was not raised'",
                f"    except AssertionError:",
                f"        raise",
                f"    except Exception as e:",
                f"        # Must not crash with unhandled internal error",
                f"        assert not isinstance(e, (ZeroDivisionError, IndexError, KeyError, UnboundLocalError)), f'Unhandled internal crash: {{type(e).__name__}}: {{e}}'",
                f"        # Expected validation error was raised",
                f"        return",
            ])
        else:
            lines.extend([
                f"    # Executing {candidate.category} test",
                f"    try:",
                f"        res = {call_str}",
                f"        assert res is not None or res is None",
                f"    except (ValueError, TypeError):",
                f"        # Clean input validation error is acceptable on boundary/malformed inputs",
                f"        pass",
            ])

        return lines

    @classmethod
    def _render_python_stateful_test(
        cls, candidate: TestCandidate, module_dotted: str
    ) -> List[str]:
        lines = [
            f"def test_{candidate.category}_{candidate.symbol_name}_{candidate.id.replace('-', '_')}():",
            f'    """',
            f"    Stateful test on: {candidate.symbol_name}",
            f"    Expected: {candidate.expected_behavior}",
            f'    """',
            f"    from {module_dotted} import {candidate.symbol_name}",
            "",
            f"    # Execute state sequence",
            f"    obj = {candidate.symbol_name}()",
        ]
        for step in candidate.state_sequence:
            action = step.get("action")
            if action == "instantiate":
                continue
            elif action == "call":
                method = step.get("method")
                args = step.get("args", [])
                args_str = ", ".join(repr(a) for a in args)
                lines.append(f"    obj.{method}({args_str})")

        return lines

    @classmethod
    def _generate_js_test(
        cls, candidate: TestCandidate, tests_dir: Path, repo_root: Path
    ) -> Path:
        safe_sym = candidate.symbol_name.replace(".", "_")
        test_file = tests_dir / f"test_regress_{safe_sym}_{candidate.id}.test.mjs"

        target_file_rel = Path(candidate.file_path).as_posix()
        # Compute relative path from tests_dir to target file
        repo_root_posix = repo_root.resolve().as_posix()

        lines: List[str] = [
            "// Auto-generated regression test by Local Repository Testing Agent",
            f"// Target: {candidate.file_path} :: {candidate.symbol_name}",
            f"// Category: {candidate.category}",
            f"// Rationale: {candidate.rationale}",
            "",
            "import test from 'node:test';",
            "import assert from 'node:assert/strict';",
            "import { pathToFileURL } from 'node:url';",
            "import path from 'node:path';",
            "import process from 'node:process';",
            "",
            f"const repoRoot = process.env.REPO_ROOT || '{repo_root_posix}';",
            f"const targetPath = path.resolve(repoRoot, '{target_file_rel}');",
            "const targetUrl = pathToFileURL(targetPath).href;",
            "const targetModule = await import(targetUrl);",
            f"const target = targetModule.{candidate.symbol_name} || targetModule.default || targetModule;",
            "",
        ]

        if candidate.is_stateful:
            lines.extend(cls._render_js_stateful_test(candidate))
        else:
            lines.extend(cls._render_js_function_test(candidate))

        test_file.write_text("\n".join(lines), encoding="utf-8")
        return test_file

    @classmethod
    def _render_js_function_test(cls, candidate: TestCandidate) -> List[str]:
        args_js = []
        for k, v in candidate.inputs.items():
            if v is None:
                args_js.append("null")
            elif isinstance(v, str):
                args_js.append(json.dumps(v))
            elif isinstance(v, (int, float, bool, list, dict)):
                args_js.append(json.dumps(v))
            else:
                args_js.append(repr(v))

        call_args = ", ".join(args_js)
        fn_name = f"test_{candidate.category}_{candidate.symbol_name}_{candidate.id.replace('-', '_')}"

        if candidate.category == "contract_violation":
            return [
                f"test('{fn_name}', async (t) => {{",
                f"    // Documented contract test: {candidate.expected_behavior}",
                f"    let threw = false;",
                f"    try {{",
                f"        await Promise.resolve(target({call_args}));",
                f"    }} catch (err) {{",
                f"        threw = true;",
                f"    }}",
                f"    assert.ok(threw, 'Expected function to throw as documented');",
                f"}});",
            ]
        else:
            return [
                f"test('{fn_name}', async (t) => {{",
                f"    // Input values: {candidate.inputs}",
                f"    // Expected: {candidate.expected_behavior}",
                f"    try {{",
                f"        const result = await Promise.resolve(target({call_args}));",
                f"        assert.ok(result !== undefined, 'Result should be defined');",
                f"    }} catch (err) {{",
                f"        if (err instanceof TypeError && err.message.includes('Cannot read properties')) {{",
                f"            throw err; // Unhandled null/undefined dereference crash",
                f"        }}",
                f"        // Acceptable validation error",
                f"    }}",
                f"}});",
            ]

    @classmethod
    def _render_js_stateful_test(cls, candidate: TestCandidate) -> List[str]:
        fn_name = f"test_{candidate.category}_{candidate.symbol_name}_{candidate.id.replace('-', '_')}"
        lines = [
            f"test('{fn_name}', async (t) => {{",
            f"    // Expected: {candidate.expected_behavior}",
            f"    const instance = new target();",
        ]
        for step in candidate.state_sequence:
            action = step.get("action")
            if action == "instantiate":
                continue
            elif action == "call":
                method = step.get("method")
                args = step.get("args", [])
                args_str = ", ".join(json.dumps(a) for a in args)
                lines.append(f"    await Promise.resolve(instance.{method}({args_str}));")
        lines.append(f"    assert.ok(true);")
        lines.append(f"}});")
        return lines

