
"""Intake module: validates input repository folder, preserves read-only integrity."""

import hashlib
import os
from pathlib import Path
from typing import Dict, List, Tuple


class IntakeError(Exception):
    """Raised when repository folder intake fails validation."""
    pass


class ProjectSource:
    """Represents a validated, read-only local project folder."""

    SUPPORTED_EXTENSIONS = {
        ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"
    }
    SUPPORTED_MANIFESTS = {
        "pyproject.toml", "setup.py", "requirements.txt", "package.json", "tsconfig.json"
    }
    IGNORED_DIRS = {
        ".git", "node_modules", "venv", ".venv", "__pycache__", ".pytest_cache",
        "dist", "build", ".next", ".nuxt", "coverage", ".tox"
    }

    def __init__(self, root_path: Path):
        self.root_path = root_path.resolve()
        self.initial_manifest = self.compute_manifest()

    def _should_ignore(self, path: Path) -> bool:
        """Check if path is inside an ignored directory."""
        rel = path.relative_to(self.root_path)
        parts = rel.parts
        for part in parts:
            if part in self.IGNORED_DIRS:
                return True
        return False

    def compute_manifest(self) -> Dict[str, str]:
        """Compute SHA-256 hashes for all non-ignored files."""
        manifest: Dict[str, str] = {}
        for root, dirs, files in os.walk(self.root_path):
            dirs[:] = [d for d in dirs if d not in self.IGNORED_DIRS]
            for file in sorted(files):
                file_path = Path(root) / file
                if self._should_ignore(file_path):
                    continue
                try:
                    rel_path = file_path.relative_to(self.root_path).as_posix()
                    hasher = hashlib.sha256()
                    with open(file_path, "rb") as f:
                        for chunk in iter(lambda: f.read(65536), b""):
                            hasher.update(chunk)
                    manifest[rel_path] = hasher.hexdigest()
                except (PermissionError, OSError) as e:
                    # Inaccessible file
                    manifest[rel_path] = f"ERROR:{e}"
        return manifest

    def verify_unchanged(self) -> Tuple[bool, List[str]]:
        """Verify that the repository remains 100% untouched."""
        current_manifest = self.compute_manifest()
        diffs: List[str] = []

        initial_keys = set(self.initial_manifest.keys())
        current_keys = set(current_manifest.keys())

        # Added files
        for added in current_keys - initial_keys:
            diffs.append(f"Added file in source: {added}")

        # Removed files
        for removed in initial_keys - current_keys:
            diffs.append(f"Removed file from source: {removed}")

        # Modified files
        for common in initial_keys & current_keys:
            if self.initial_manifest[common] != current_manifest[common]:
                diffs.append(f"Modified file in source: {common}")

        is_unchanged = len(diffs) == 0
        return is_unchanged, diffs


def validate_repository_folder(path_str: str) -> ProjectSource:
    """
    Validate a local path string.
    Rejects missing, unreadable, non-directory, empty, or unsupported input with useful explanations.
    """
    if not path_str or not path_str.strip():
        raise IntakeError("Repository folder path cannot be empty.")

    target_path = Path(path_str).expanduser()

    if not target_path.exists():
        raise IntakeError(f"Specified path does not exist: '{target_path}'")

    if not target_path.is_dir():
        raise IntakeError(f"Specified path is a file, not a directory: '{target_path}'")

    # Readability check
    try:
        entries = list(target_path.iterdir())
    except PermissionError as e:
        raise IntakeError(f"Permission denied: cannot read repository directory '{target_path}': {e}")
    except OSError as e:
        raise IntakeError(f"Failed to access repository directory '{target_path}': {e}")

    if not entries:
        raise IntakeError(f"Repository directory is completely empty: '{target_path}'")

    # Check for supported code or manifests
    supported_files = []
    has_manifest = False
    for root, dirs, files in os.walk(target_path):
        dirs[:] = [d for d in dirs if d not in ProjectSource.IGNORED_DIRS]
        for f in files:
            p = Path(root) / f
            ext = p.suffix.lower()
            if ext in ProjectSource.SUPPORTED_EXTENSIONS:
                supported_files.append(p)
            if f in ProjectSource.SUPPORTED_MANIFESTS:
                has_manifest = True

    if not supported_files and not has_manifest:
        raise IntakeError(
            f"Unsupported project at '{target_path}'. No Python (.py) or JavaScript/TypeScript "
            "(.js, .ts, .mjs) source files or project manifests (package.json, pyproject.toml, "
            "setup.py, requirements.txt) were detected."
        )

    return ProjectSource(target_path)

