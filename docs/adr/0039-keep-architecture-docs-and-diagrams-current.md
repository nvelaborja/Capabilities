# 0039. Keep architecture docs and diagrams current, and teach every technology

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

The project now spans several technologies: Python packages in a uv workspace, DuckDB, dbt, Parquet, FastAPI, React and Cytoscape.js. Each data platform milestone adds more ([0033](0033-build-a-python-data-platform-around-the-graph.md)). It is a learning project, so how each piece works matters as much as what it does. Architecture docs written once go stale quickly, and diagrams drawn by hand are rarely redrawn.

## Decision

We will keep the architecture documented in the repository, update it in the same pull request as every change it describes, and teach each technology as we adopt it.

- **`docs/architecture/`** holds:
  - an overview of the system;
  - a reference for the data pipeline (inputs, stages, tables, outputs, checks, commands);
  - one page per technology under `technologies/`, with the same sections: what it is, how it works, how we use it, where it lives, things to know, and further reading with links to official documentation.
- **Diagrams are code**, written in [LikeC4](../architecture/technologies/likec4.md) in `docs/architecture/diagrams/`:
  - one model of the whole system;
  - an `index` view, the master diagram of everything that exists;
  - focused views such as `pipeline`.

  `npm run build` in `web/` builds them into the web app's output, and the API server hosts them at `/architecture/`.
- **Every pull request** that changes the architecture, the data flow, a dependency's role, or the technology:
  - updates the LikeC4 model and every view it affects, adding new parts to the `index` view;
  - updates the overview, and the data pipeline reference if data flow changed;
  - adds a technology page when it introduces a technology, written to teach it, not just to name it.

  A pull request that changes none of these says so in its description. The pull request template asks.
- **Model only what exists.** Planned parts join the diagrams in the pull request that builds them. Plans live in the plan and the ADRs.
- **CI checks the diagrams**: the web build validates and builds the LikeC4 model, so a broken model fails the pull request.

## Consequences

- Reviewers see the architecture change next to the code that changes it, and the diagrams can't drift far from the code.
- Every PR costs a little more effort, most of it small edits to existing pages.
- New contributors, and the maintainer learning a new tool, have one place to start, with links to go deeper.
- LikeC4 becomes a build-time dependency of the web app. If it is ever abandoned, the model is plain text and can be ported.
- CI can check that the model is valid, but not that it is accurate. Accuracy is the reviewer's job, helped by the template.

## Alternatives considered

- **Docs in a wiki or the maintainer's notes.** Easier to write, but separate from review, so they go stale, and other contributors can't see them.
- **Diagrams drawn by hand (draw.io, Excalidraw, images).** Flexible, but every change means redrawing, and nothing keeps several diagrams consistent with each other.
- **Mermaid or PlantUML.** Diagrams as code, with wide rendering support, but each diagram is drawn on its own. LikeC4 keeps one model behind every view and builds an interactive site.
- **Structurizr.** The reference C4 tool and a single model too, but it is Java-based and its site is harder to host from our own server.
- **Document only at milestones.** Less overhead, but each milestone would then need its own documentation project.
