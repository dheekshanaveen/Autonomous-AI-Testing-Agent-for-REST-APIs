"""Inventory module: inspects Python and JavaScript/TypeScript projects."""

import ast
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from local_agent.intake import ProjectSource
from local_agent.models import CodeSymbol, ContractInfo, ParameterInfo, ProjectInventory


class PythonInspector:
    """Inspects Python source code via AST analysis and docstring parsing."""

    @staticmethod
    def _parse_docstring_contracts(docstring: Optional[str]) -> List[ContractInfo]:
        contracts: List[ContractInfo] = []
        if not docstring:
            return contracts

        # Match "Raises: <Exception> if <condition>" or ":raises <Exception>: <condition>"
        raises_patterns = [
            r"(?:Raises|raises|RAISES):\s*(\w+)(?::|\s+if|\s+when|\s+-)?\s*([^\n\r.]+)?",
            r":raises\s+(\w+):\s*([^\n\r.]+)?",
            r"@raises\s+(\w+)\s*([^\n\r.]+)?",
        ]
        for pattern in raises_patterns:
            for match in re.finditer(pattern, docstring):
                exc_type = match.group(1)
                condition = (match.group(2) or "").strip()
                contracts.append(
                    ContractInfo(
                        kind="raises",
                        target=exc_type,
                        condition=condition,
                        raw_text=match.group(0).strip(),
                    )
                )

        # Match requirements/preconditions: "Requires: ...", "Precondition: ...", "Must not be ..."
        req_patterns = [
            r"(?:Requires|Precondition|requires|must|MUST|Note):\s*([^\n\r]+)",
            r"([A-Za-z0-9_]+)\s+must\s+(?:not\s+be\s+|be\s+)([^\n\r]+)",
        ]
        for pattern in req_patterns:
            for match in re.finditer(pattern, docstring):
                contracts.append(
                    ContractInfo(
                        kind="requires",
                        target="",
                        condition=match.group(1).strip(),
                        raw_text=match.group(0).strip(),
                    )
                )

        return contracts

    @classmethod
    def _analyze_ast_risks(cls, node: ast.AST, param_names: Set[str]) -> List[str]:
        risks: List[str] = []

        has_div_zero_check = False
        has_none_check = False
        has_empty_check = False

        # Scan for guards (If statements)
        for child in ast.walk(node):
            if isinstance(child, ast.If):
                # Check for `if x == 0` or `if not x` or `if x is None`
                test_dump = ast.dump(child.test)
                if "Constant(value=0)" in test_dump:
                    has_div_zero_check = True
                if "Constant(value=None)" in test_dump:
                    has_none_check = True
                if "len(" in test_dump or "not" in test_dump:
                    has_empty_check = True

        # Scan for risky operations
        for child in ast.walk(node):
            # Division or modulo
            if isinstance(child, ast.BinOp) and isinstance(child.op, (ast.Div, ast.FloorDiv, ast.Mod)):
                if isinstance(child.right, ast.Name) and child.right.id in param_names:
                    if not has_div_zero_check and "zero_division" not in risks:
                        risks.append("zero_division")

            # Sequence indexing or pop
            if isinstance(child, ast.Subscript):
                if isinstance(child.value, ast.Name) and child.value.id in param_names:
                    if not has_empty_check and "empty_sequence" not in risks:
                        risks.append("empty_sequence")
            elif isinstance(child, ast.Call):
                if isinstance(child.func, ast.Attribute) and child.func.attr == "pop":
                    if isinstance(child.func.value, ast.Name) and child.func.value.id in param_names:
                        if not has_empty_check and "empty_sequence" not in risks:
                            risks.append("empty_sequence")

            # Direct attribute dereference on parameter
            if isinstance(child, ast.Attribute):
                if isinstance(child.value, ast.Name) and child.value.id in param_names:
                    if not has_none_check and "none_dereference" not in risks:
                        risks.append("none_dereference")

        return risks

    @classmethod
    def inspect_file(cls, file_path: Path, rel_path: str) -> List[CodeSymbol]:
        symbols: List[CodeSymbol] = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content, filename=str(file_path))
        except (SyntaxError, UnicodeDecodeError):
            return symbols

        for node in tree.body:
            # Standalone functions
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_") and not node.name.startswith("__init__"):
                    continue
                symbols.append(cls._extract_function_symbol(node, rel_path, parent_class=None))

            # Classes
            elif isinstance(node, ast.ClassDef):
                if node.name.startswith("_"):
                    continue
                docstring = ast.get_docstring(node)
                class_symbol = CodeSymbol(
                    name=node.name,
                    file_path=rel_path,
                    line_number=node.lineno,
                    kind="class",
                    language="python",
                    docstring=docstring,
                    contracts=cls._parse_docstring_contracts(docstring),
                )
                symbols.append(class_symbol)

                # Class methods
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_symbol = cls._extract_function_symbol(
                            item, rel_path, parent_class=node.name
                        )
                        symbols.append(method_symbol)

        return symbols

    @classmethod
    def _extract_function_symbol(
        cls,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        rel_path: str,
        parent_class: Optional[str] = None,
    ) -> CodeSymbol:
        params: List[ParameterInfo] = []
        param_names: Set[str] = set()

        # Handle defaults mapping
        args = node.args.args
        defaults = node.args.defaults
        num_defaults = len(defaults)
        offset = len(args) - num_defaults

        for idx, arg in enumerate(args):
            if parent_class and arg.arg == "self":
                continue
            param_names.add(arg.arg)
            type_ann = ast.unparse(arg.annotation) if arg.annotation else None
            default_val = None
            has_default = False
            if idx >= offset:
                default_idx = idx - offset
                default_val = ast.unparse(defaults[default_idx])
                has_default = True

            params.append(
                ParameterInfo(
                    name=arg.arg,
                    type_annotation=type_ann,
                    default_value=default_val,
                    has_default=has_default,
                )
            )

        return_type = ast.unparse(node.returns) if node.returns else None
        docstring = ast.get_docstring(node)
        contracts = cls._parse_docstring_contracts(docstring)
        risks = cls._analyze_ast_risks(node, param_names)

        return CodeSymbol(
            name=node.name,
            file_path=rel_path,
            line_number=node.lineno,
            kind="method" if parent_class else "function",
            language="python",
            parent_class=parent_class,
            parameters=params,
            return_type=return_type,
            docstring=docstring,
            contracts=contracts,
            risk_flags=risks,
        )


class JavaScriptInspector:
    """Inspects JavaScript and TypeScript source files."""

    FUNCTION_PATTERN = re.compile(
        r"(?:export\s+(?:async\s+)?)?function\s+([A-Za-z0-9_$]+)\s*\(([^)]*)\)",
        re.MULTILINE,
    )
    ARROW_FUNCTION_PATTERN = re.compile(
        r"(?:export\s+)?const\s+([A-Za-z0-9_$]+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>",
        re.MULTILINE,
    )
    CLASS_PATTERN = re.compile(
        r"(?:export\s+)?class\s+([A-Za-z0-9_$]+)(?:\s+extends\s+[A-Za-z0-9_$]+)?\s*\{",
        re.MULTILINE,
    )
    METHOD_PATTERN = re.compile(
        r"^\s*(?:async\s+)?([A-Za-z0-9_$]+)\s*\(([^)]*)\)\s*\{",
        re.MULTILINE,
    )

    @classmethod
    def inspect_file(cls, file_path: Path, rel_path: str) -> List[CodeSymbol]:
        symbols: List[CodeSymbol] = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except UnicodeDecodeError:
            return symbols

        ext = file_path.suffix.lower()
        language = "typescript" if ext in {".ts", ".tsx"} else "javascript"

        lines = content.splitlines()

        # Extract functions
        for match in cls.FUNCTION_PATTERN.finditer(content):
            name = match.group(1)
            raw_params = match.group(2)
            line_no = content[: match.start()].count("\n") + 1
            if name.startswith("_"):
                continue
            docstring = cls._find_preceding_jsdoc(lines, line_no - 1)
            params = cls._parse_params(raw_params)
            risks = cls._find_risks(content[match.start() : match.start() + 500], params)
            symbols.append(
                CodeSymbol(
                    name=name,
                    file_path=rel_path,
                    line_number=line_no,
                    kind="function",
                    language=language,
                    parameters=params,
                    docstring=docstring,
                    contracts=cls._parse_jsdoc_contracts(docstring),
                    risk_flags=risks,
                )
            )

        # Extract arrow functions
        for match in cls.ARROW_FUNCTION_PATTERN.finditer(content):
            name = match.group(1)
            raw_params = match.group(2)
            line_no = content[: match.start()].count("\n") + 1
            if name.startswith("_"):
                continue
            docstring = cls._find_preceding_jsdoc(lines, line_no - 1)
            params = cls._parse_params(raw_params)
            risks = cls._find_risks(content[match.start() : match.start() + 500], params)
            symbols.append(
                CodeSymbol(
                    name=name,
                    file_path=rel_path,
                    line_number=line_no,
                    kind="function",
                    language=language,
                    parameters=params,
                    docstring=docstring,
                    contracts=cls._parse_jsdoc_contracts(docstring),
                    risk_flags=risks,
                )
            )

        # Extract classes and methods
        for match in cls.CLASS_PATTERN.finditer(content):
            class_name = match.group(1)
            line_no = content[: match.start()].count("\n") + 1
            docstring = cls._find_preceding_jsdoc(lines, line_no - 1)
            symbols.append(
                CodeSymbol(
                    name=class_name,
                    file_path=rel_path,
                    line_number=line_no,
                    kind="class",
                    language=language,
                    docstring=docstring,
                    contracts=cls._parse_jsdoc_contracts(docstring),
                )
            )

        return symbols

    @staticmethod
    def _find_preceding_jsdoc(lines: List[str], line_idx: int) -> Optional[str]:
        """Find JSDoc block right above the symbol definition."""
        i = line_idx - 1
        while i >= 0 and not lines[i].strip():
            i -= 1
        if i >= 0 and "*/" in lines[i]:
            doc_lines = []
            while i >= 0:
                doc_lines.insert(0, lines[i])
                if "/**" in lines[i]:
                    break
                i -= 1
            return "\n".join(doc_lines)
        return None

    @staticmethod
    def _parse_jsdoc_contracts(docstring: Optional[str]) -> List[ContractInfo]:
        contracts: List[ContractInfo] = []
        if not docstring:
            return contracts
        for match in re.finditer(r"@throws\s+\{?(\w+)\}?\s*([^\n\r*]+)?", docstring):
            contracts.append(
                ContractInfo(
                    kind="raises",
                    target=match.group(1),
                    condition=(match.group(2) or "").strip(),
                    raw_text=match.group(0).strip(),
                )
            )
        return contracts

    @staticmethod
    def _parse_params(raw_params: str) -> List[ParameterInfo]:
        params: List[ParameterInfo] = []
        for p in raw_params.split(","):
            p = p.strip()
            if not p:
                continue
            has_default = "=" in p
            default_val = None
            type_ann = None
            if has_default:
                parts = p.split("=", 1)
                p = parts[0].strip()
                default_val = parts[1].strip()
            if ":" in p:
                parts = p.split(":", 1)
                p = parts[0].strip()
                type_ann = parts[1].strip()
            params.append(
                ParameterInfo(
                    name=p,
                    type_annotation=type_ann,
                    default_value=default_val,
                    has_default=has_default,
                )
            )
        return params

    @staticmethod
    def _find_risks(snippet: str, params: List[ParameterInfo]) -> List[str]:
        risks: List[str] = []
        param_names = [p.name for p in params]
        for name in param_names:
            if re.search(rf"[/%]\s*{re.escape(name)}\b", snippet):
                if "zero_division" not in risks:
                    risks.append("zero_division")
            if re.search(rf"{re.escape(name)}\.[A-Za-z0-9_$]+", snippet):
                if "js_null_undefined" not in risks:
                    risks.append("js_null_undefined")
            if re.search(rf"{re.escape(name)}\s*\[0\]|{re.escape(name)}\.pop\(", snippet):
                if "empty_sequence" not in risks:
                    risks.append("empty_sequence")
        return risks


def build_project_inventory(source: ProjectSource) -> ProjectInventory:
    """Build an inventory of languages, entry points, tests, and code symbols."""
    repo_root = source.root_path
    languages: Set[str] = set()
    manifests: List[str] = []
    source_files: List[str] = []
    test_files: List[str] = []
    test_frameworks: Set[str] = set()
    symbols: List[CodeSymbol] = []
    setup_notes: List[str] = []

    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in ProjectSource.IGNORED_DIRS]
        for f in sorted(files):
            file_path = Path(root) / f
            rel_path = file_path.relative_to(repo_root).as_posix()
            ext = file_path.suffix.lower()

            if f in ProjectSource.SUPPORTED_MANIFESTS:
                manifests.append(rel_path)
                if f in {"pyproject.toml", "setup.py", "requirements.txt"}:
                    languages.add("python")
                if f in {"package.json", "tsconfig.json"}:
                    languages.add("javascript")

            is_test = (
                "test" in f.lower()
                or "spec" in f.lower()
                or any(part in {"tests", "__tests__", "test"} for part in file_path.parts)
            )

            if ext == ".py":
                languages.add("python")
                if is_test:
                    test_files.append(rel_path)
                    test_frameworks.add("pytest")
                else:
                    source_files.append(rel_path)
                    symbols.extend(PythonInspector.inspect_file(file_path, rel_path))

            elif ext in {".js", ".jsx", ".mjs", ".cjs"}:
                languages.add("javascript")
                if is_test:
                    test_files.append(rel_path)
                    test_frameworks.add("node:test")
                else:
                    source_files.append(rel_path)
                    symbols.extend(JavaScriptInspector.inspect_file(file_path, rel_path))

            elif ext in {".ts", ".tsx"}:
                languages.add("typescript")
                if is_test:
                    test_files.append(rel_path)
                    test_frameworks.add("node:test")
                else:
                    source_files.append(rel_path)
                    symbols.extend(JavaScriptInspector.inspect_file(file_path, rel_path))

    if not test_frameworks:
        if "python" in languages:
            test_frameworks.add("pytest")
        if "javascript" in languages or "typescript" in languages:
            test_frameworks.add("node:test")

    return ProjectInventory(
        repo_path=str(repo_root),
        languages=sorted(list(languages)),
        manifests=sorted(manifests),
        source_files=sorted(source_files),
        test_files=sorted(test_files),
        test_frameworks=sorted(list(test_frameworks)),
        symbols=symbols,
        setup_notes=setup_notes,
    )

