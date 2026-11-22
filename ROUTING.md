# Component routing

This describes the intended local-folder workflow. It is a map for implementation, not a claim that every component already exists.

| Stage | Input | Output | Connects to |
| --- | --- | --- | --- |
| Folder intake | Local path | Validated, read-only project source | Project inventory |
| Project inventory | Source and manifests | Languages, entry points, tests, setup information | Test candidate analysis |
| Test candidate analysis | Code, tests, docs | Candidate behaviors and expected outcomes | Test generation |
| Test generation | Candidate and project context | Focused regression test in separate output folder | Isolated runner |
| Isolated runner | Project snapshot and generated test | Exit status, output, observed behavior | Replay and classification |
| Replay and classification | First run and repeated run | Verified failure, lead, or setup gap | Report writer |
| Report writer | Evidence and coverage | Readable report and structured result | User |

The entire chain operates on the selected local repository inside an isolated environment. Reports and generated tests are written outside that repository. The current agent/ modules implement an earlier REST API prototype; reusable pieces can be connected to this workflow when they match its needs.
