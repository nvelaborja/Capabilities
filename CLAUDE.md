# CLAUDE.md

Guidance for AI coding agents working in this repository.

## What this is

Capabilities is an open knowledge graph of what it physically takes to make and do things. It answers three questions: what would it take (Q1), what else could they do (Q2), and could it have been done this way (Q3). Start with [README.md](README.md), then [docs/data-format.md](docs/data-format.md).

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
uv run pytest                    # tests
uv run capabilities validate     # check every data file; run before any data PR
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
npm run build                    # web/dist, which `capabilities serve` hosts at /
```

## Layout

- `schema/`: JSON Schemas for every data file type
- `data/`: the graph (quantities, things, verbs, routes, profiles), licensed CC BY 4.0
- `examples/jobs/`: feasibility-check jobs; `examples/README.md` holds worked results that tests check
- `src/capabilities/`: `graph.py` (loading), `validate.py`, `tristate.py`, `reasoner.py` (the three questions), `levels.py` (tech levels), `views.py` (display-ready shapes for the web UI), `cli.py`, `server.py` (API under `/api`)
- `web/src/`: `api/` (typed client), `graph/` (Cytoscape elements, styles, statuses, tech-tree layout, focus mode, summary nodes), `detail/` (detail pane for nodes, lines and summaries: route checklists, drill-down, expand-all dialog), `chips/` (node-like chips used in every list), `panes/` (side pane, lists, dialog), `search/`, `lib/bounded.ts` (top N, the rest summarised by type), `layout/` (resizable panes), `legend/`, `state/` (selection history and links, explore and explain hooks, breadcrumb trail, theme), `catalog.ts` (labels for any id)
- `tests/`: pytest suite
- `docs/`: data format, reasoning rules, and ADRs

## Data rules

- **Never invent numbers or citations.** Unknown is fine; guessing is not. Use `basis: unknown` or a `TODO-source` note instead ([ADR 0008](docs/adr/0008-record-the-basis-of-every-number.md)).
- Every route cites at least one reference, with an honest `status` and a `supports` statement.
- Know-how never gates a route ([ADR 0005](docs/adr/0005-know-how-never-gates-reachability.md)). Techniques are descriptive labels only.
- Missing data must produce "maybe", never "no" ([ADR 0007](docs/adr/0007-compare-ranges-with-three-answers.md)).
- If you change data that the worked examples depend on, update `examples/README.md` and the tests that check it.

## Code conventions

- Python 3.12 with type hints. Keep functions small and named so callers read like prose.
- Comments explain why, not what.
- Tests describe behavior. When a test fails, fix the code unless the test is wrong, and say why.
- Conventional Commits (`feat:`, `fix:`, `docs:`...), lines under 120 characters.
- Work on a branch and open a draft pull request. Never push to `main`.
- Check a dependency's license against GPL-3.0 before adding it ([ADR 0014](docs/adr/0014-license-code-gpl-and-data-cc-by.md)).
- Web: colours come from CSS custom properties in `web/src/theme.css` (light and dark); the graph reads them, so never hard-code colours in `graph/styles.ts`. A coloured strip with an emoji shows a node's type and its border shows its status ([ADR 0022](docs/adr/0022-type-strip-with-emoji-on-neutral-nodes.md)); status must never rely on colour alone, and nothing may be available only on hover ([ADR 0019](docs/adr/0019-desktop-first-mobile-ready.md)).
