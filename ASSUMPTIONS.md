# Working assumptions

These are assumptions, not confirmed product facts. Update each entry as testing gives evidence.

| Assumption | How we will check it |
| --- | --- |
| A selected project folder is readable and contains enough source or project metadata to identify a language. | Try repositories with and without standard manifests. |
| A disposable local runner can inspect and test a project without changing its source folder. | Compare folder contents before and after a scan. |
| Existing tests and documentation often provide enough expected behavior to generate useful new cases. | Measure the proportion of unfamiliar projects that yield runnable tests. |
| Python and JavaScript/TypeScript cover enough variety for a strong first evaluation. | Evaluate on several unrelated projects in both ecosystems. |
| A free local model can improve test selection, but is not required for a verified result. | Compare runs with the model enabled and disabled. |
| Some projects will need services or data the tool cannot infer automatically. | Report these as setup gaps and measure their frequency. |

Do not turn an assumption into a verified claim without an experiment or source.
