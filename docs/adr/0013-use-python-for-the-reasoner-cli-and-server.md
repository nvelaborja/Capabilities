# 0013. Use Python for the reasoner, CLI and local API server

- **Status:** Accepted
- **Date:** 2026-11-04 (recorded 2026-11-05)

## Context

The reasoner needs graph algorithms, three-valued logic and unit-aware arithmetic. The likely contributors are scientists and hobbyists. Hosting can wait; running locally is enough for now.

## Decision

- **Python 3.12**, managed with **uv** (which also installs Python).
- A `capabilities` CLI: `validate`, `need`, `explore`, `check`, `serve`. Every command has `--json`.
- A local **FastAPI** server (`capabilities serve`), with interactive docs at `/docs`.
- **pytest** tests, run in GitHub Actions on every pull request.
- Cloud hosting and a web front end later ([0015](0015-build-the-web-front-end-with-react-and-cytoscape.md)).

## Consequences

- Python is widely known in science, so it suits contributors and AI skills alike.
- The front end needs a separate language (TypeScript). Running the reasoner in the browser later would need Pyodide or a port.

## Alternatives considered

- **TypeScript everywhere.** One language with the front end, and the reasoner could run in the browser. Rejected: less familiar to scientific contributors.
- **Rust.** Fast, but a high barrier for contributors, and speed isn't the constraint.
- **Prolog or Datalog.** Natural for the logic, but awkward for quantities and a barrier for contributors.
