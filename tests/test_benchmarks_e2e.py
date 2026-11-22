"""End-to-End showcase and acceptance criteria verification."""

from pathlib import Path
from benchmarks.evaluator import run_benchmark_evaluation


def test_showcase_and_acceptance_criteria():
    base_dir = Path(__file__).resolve().parent.parent
    eval_result = run_benchmark_evaluation(base_dir)

    # Acceptance Criterion 1: A clean scan leaves the selected folder unchanged
    assert eval_result["all_source_folders_untouched"] is True, "Source folder integrity failed"

    # Acceptance Criterion 2: A generated test fails on known faulty and passes on corrected
    python_target = [t for t in eval_result["targets"] if t["language"] == "python" and t["fixes_confirmed"] is not None][0]
    assert python_target["fixes_confirmed"] is True, "Python fix verification failed"

    js_target = [t for t in eval_result["targets"] if t["language"] == "javascript" and t["fixes_confirmed"] is not None][0]
    assert js_target["fixes_confirmed"] is True, "JavaScript fix verification failed"

    # Acceptance Criterion 3: Report does not mark suggestion as verified when setup, execution, or replay fails
    assert eval_result["total_false_alarms"] == 0, "False alarms detected in verified failures"

    unsupported_target = [t for t in eval_result["targets"] if "Unsupported" in t["target_name"]][0]
    assert unsupported_target["setup_success"] is False, "Setup failure was not reported"
    assert unsupported_target["verified_failures"] == 0, "Unsupported target had false verified failures"
    assert unsupported_target["setup_gaps"] > 0, "Setup gap was not detected"

    # Acceptance Criterion 4: Showcase covers unfamiliar Python and JS/TS projects
    target_names = [t["target_name"] for t in eval_result["targets"]]
    assert any("Python" in n for n in target_names)
    assert any("JavaScript" in n for n in target_names)
    assert any("Unsupported" in n for n in target_names)

