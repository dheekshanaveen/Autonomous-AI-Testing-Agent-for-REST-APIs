"""Tests for intake module."""

from pathlib import Path
import pytest
from local_agent.intake import IntakeError, validate_repository_folder


def test_intake_valid_python_repo(sample_python_repo_path):
    source = validate_repository_folder(str(sample_python_repo_path))
    assert source.root_path == sample_python_repo_path.resolve()
    assert len(source.initial_manifest) > 0

    is_unchanged, diffs = source.verify_unchanged()
    assert is_unchanged is True
    assert diffs == []


def test_intake_nonexistent_path():
    with pytest.raises(IntakeError, match="does not exist"):
        validate_repository_folder("C:/nonexistent_folder_xyz_123")


def test_intake_file_path(temp_dir):
    file_path = temp_dir / "sample_file.txt"
    file_path.write_text("hello", encoding="utf-8")
    with pytest.raises(IntakeError, match="is a file, not a directory"):
        validate_repository_folder(str(file_path))


def test_intake_empty_folder(temp_dir):
    with pytest.raises(IntakeError, match="completely empty"):
        validate_repository_folder(str(temp_dir))


def test_intake_unsupported_project(temp_dir):
    # Folder with only images or text files
    txt_file = temp_dir / "notes.txt"
    txt_file.write_text("some notes", encoding="utf-8")
    with pytest.raises(IntakeError, match="No Python .* or JavaScript/TypeScript .* source files"):
        validate_repository_folder(str(temp_dir))


def test_intake_source_immutability_detection(temp_dir):
    # Setup a mini valid repo
    py_file = temp_dir / "app.py"
    py_file.write_text("def hello(): return 'world'", encoding="utf-8")

    source = validate_repository_folder(str(temp_dir))
    assert source.verify_unchanged()[0] is True

    # Mutate a file
    py_file.write_text("def hello(): return 'mutated'", encoding="utf-8")
    is_unchanged, diffs = source.verify_unchanged()
    assert is_unchanged is False
    assert any("Modified file in source" in d for d in diffs)

    # Add a file
    extra = temp_dir / "extra.py"
    extra.write_text("x = 1", encoding="utf-8")
    is_unchanged, diffs = source.verify_unchanged()
    assert is_unchanged is False
    assert any("Added file in source" in d for d in diffs)

