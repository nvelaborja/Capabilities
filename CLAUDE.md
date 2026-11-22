# CLAUDE.md

Guidance for AI coding agents working in this repository.

## What this is

Capabilities is a free, non-commercial knowledge graph of what it physically takes to make and do things. It answers three questions: what would it take (Q1), what else could they do (Q2), and could it have been done this way (Q3). Start with [README.md](README.md), then [docs/data-format.md](docs/data-format.md).

## Design decisions (ADRs)

Design decisions are recorded in [docs/adr/](docs/adr/README.md). They are binding.

- **Read the ADR index before changing** the data model, schemas, reasoning rules, API, UI behavior, stack or licenses. Read the ADRs that touch your change.
- **Don't contradict an accepted ADR silently.** If a task conflicts with one, stop and ask the user, or propose a new ADR that supersedes it.
- **Record new decisions.** If your change makes a significant design decision (see [0001](docs/adr/0001-record-architecture-decisions.md)), add an ADR in the same pull request: copy `docs/adr/template.md` to the next number, and add a row to the index.
- **Never rewrite an accepted ADR.** To change one, write a new ADR that supersedes it, and change only the old ADR's status line. Proposed ADRs can be edited.
- When you implement a proposed ADR and the user confirms it, change its status to Accepted.

## Commands

```bash
uv sync                          # install (uv installs Python 3.12)
uv run pytest                    # tests (all packages; builds the graph once into a temp dir)
uv run capabilities validate     # check every data file; run before any data PR
uv run capabilities build        # build the graph with dbt into build/graph (the questions and server rebuild when stale)
uv run capabilities need steel   # Q1
uv run capabilities explore --profile middle-kingdom-egypt   # Q2
uv run capabilities check granite-slab-saw-cut --profile middle-kingdom-egypt   # Q3
uv run capabilities serve        # local API at http://127.0.0.1:8000/docs
```

Web app (`web/`, React + TypeScript + Cytoscape.js, see [ADR 0015](docs/adr/0015-build-the-web-front-end-with-react-and-cytoscape.md)); needs Node 22+:

```bash
cd web
npm ci                           # install
npm run dev                      # dev server on :5173, forwarding /api to `capabilities serve` on :8000
npm test                         # Vitest
npm run lint && npm run typecheck
npm run build                    # web/dist (app, plus architecture diagrams in web/dist/architecture), which `capabilities serve` hosts at /
npm run diagrams                 # live preview of the LikeC4 diagrams in docs/architecture/diagrams
```

## Layout

- `schema/`: JSON Schemas for every data file type
- `data/`: the graph (quantities, things, verbs, routes, profiles), licensed CC BY-NC-SA 4.0. Things include sources (where a resource is found); extraction routes take materials from them (ADR 0032)
- `examples/jobs/`: feasibility-check jobs; `examples/README.md` holds worked results that tests check
- `packages/core/src/capabilities/`: `graph.py` (the in-memory graph; `Graph.from_curated` reads the YAML), `built.py` (reading the built graph, freshness), `validate.py`, `tristate.py`, `reasoner.py` (the three questions), `levels.py` (tech levels), `views.py` (display-ready shapes for the web UI), `credits.py` (the works cited in CREDITS.md), `cli.py`
- `packages/api/src/capabilities_api/server.py`: the API under `/api`, which also hosts the web app
- `pipeline/`: `src/capabilities_pipeline/build.py` (loads the curated layer into DuckDB, runs dbt, writes the manifest) and `dbt/` (sources, staging, marts written as Parquet). See [ADR 0038](docs/adr/0038-serve-the-app-from-a-built-graph-artifact.md)
- `web/src/`: `api/` (typed client), `graph/` (Cytoscape elements, styles, statuses, tech-tree layout, focus mode, hiding busy nodes' extra lines), `detail/` (detail pane for nodes and lines: route checklists, drill-down, expand-all dialog), `chips/` (node-like chips used in every list), `panes/` (side pane, lists, dialog), `search/`, `lib/bounded.ts` (top N, the rest summarised by type), `layout/` (resizable panes), `legend/`, `state/` (selection history and links, explore and explain hooks, breadcrumb trail, theme), `catalog.ts` (labels for any id)
- Tests live beside each package (`packages/*/tests`, `pipeline/tests`); shared fixtures are in the root `conftest.py`
- `build/`: generated (warehouse, built graph, dbt logs); never commit it
- `docs/`: `architecture/` (overview, data pipeline, technology guides, LikeC4 diagrams), data format, reasoning rules, and ADRs

## Architecture docs

- Every pull request that changes the architecture, the data flow or the technology updates `docs/architecture/` in the same PR ([ADR 0039](docs/adr/0039-keep-architecture-docs-and-diagrams-current.md)): the LikeC4 model and views in `docs/architecture/diagrams/` (new parts go in the `index` view), the overview, the data pipeline reference if data flow changed, and a teaching page under `technologies/` for any new technology (same sections as the others, links to official docs checked to work).
- Model only what exists; planned parts join the diagrams when they are built.
- `cd web && npm run diagrams:check` validates the model; `npm run build` builds it into `web/dist/architecture`, which `capabilities serve` hosts at `/architecture/`.

## Data rules

- **Never invent numbers or citations.** Unknown is fine; guessing is not. Use `basis: unknown` or a `TODO-source` note instead ([ADR 0008](docs/adr/0008-record-the-basis-of-every-number.md)).
- Every route cites at least one reference, with an honest `status` and a `supports` statement.
- Know-how never gates a route ([ADR 0005](docs/adr/0005-know-how-never-gates-reachability.md)). Techniques are descriptive labels only.
- Missing data must produce "maybe", never "no" ([ADR 0007](docs/adr/0007-compare-ranges-with-three-answers.md)).
- A natural resource that takes tools to get (timber, quarried stone, mined ore) is `origin: extracted`, with a `source` saying where it is found and a cited extraction route. Only materials gathered by hand as they are stay `origin: natural` ([ADR 0032](docs/adr/0032-extract-materials-from-sources-by-routes.md)).
- The YAML in `data/` is the curated layer; the app reads the graph built from it ([ADR 0034](docs/adr/0034-build-the-graph-from-upstream-datasets-and-a-curated-layer.md), [ADR 0038](docs/adr/0038-serve-the-app-from-a-built-graph-artifact.md)). Every fact must have provenance: curated facts cite references (above); upstream facts, from milestone 1, carry their dataset and record. Never edit upstream sources, override them in the curated layer instead.
- If you change data that the worked examples depend on, update `examples/README.md` and the tests that check it.

## Code conventions

- Python 3.12 with type hints. Keep functions small and named so callers read like prose.
- Comments explain why, not what.
- Tests describe behavior. When a test fails, fix the code unless the test is wrong, and say why.
- Conventional Commits (`feat:`, `fix:`, `docs:`...), lines under 120 characters.
- Work on a branch and open a draft pull request. Never push to `main`.
- The project is for non-commercial use only: code under PolyForm Noncommercial 1.0.0, data under CC BY-NC-SA 4.0 ([ADR 0037](docs/adr/0037-license-the-project-for-non-commercial-use-only.md)). Check a dependency's or dataset's license before adding it, never call the project "open source", and add every new dataset or cited work to [CREDITS.md](CREDITS.md) (`uv run capabilities credits` regenerates the works cited).
- Web: colours come from CSS custom properties in `web/src/theme.css` (light and dark); the graph reads them, so never hard-code colours in `graph/styles.ts`. A coloured strip with an emoji shows a node's type and its border shows its status ([ADR 0022](docs/adr/0022-type-strip-with-emoji-on-neutral-nodes.md)); status must never rely on colour alone, and nothing may be available only on hover ([ADR 0019](docs/adr/0019-desktop-first-mobile-ready.md)).
