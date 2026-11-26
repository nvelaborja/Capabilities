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
cd pipeline && uv run dg dev     # Dagster UI at http://localhost:3000: the build as assets, lineage, checks, runs
cd pipeline && uv run dg launch --assets 'upstream/mrds_deposits'   # download an MRDS snapshot (only Dagster downloads)
cd pipeline && uv run dg launch --assets 'upstream/pleiades_places'   # download Pleiades' daily dump of ancient places
cd pipeline && uv run dg launch --assets 'upstream/wikidata_quantities'   # query Wikidata for the crosswalked things
cd pipeline && uv run dg launch --assets 'upstream/reference_candidates'   # look every cited work up in OpenAlex and Crossref
uv run capabilities backup       # make newer downloads the cold backups in snapshots/ (commit them)
uv run capabilities queue        # the curation queue: the gaps the last build found
cd pipeline && uv run dg launch --job agent_curation --config-json '{"ops": {"curate": {"config": {"items": 5}}}}'   # agents propose ore rows (uses your Claude plan; ADR 0048)
cd pipeline && uv run dg launch --job agent_curation --config-json '{"ops": {"curate": {"config": {"task": "route_sources", "items": 5}}}}'   # agents quote sources for unverified routes (ADR 0049)
cd pipeline && uv run dg launch --assets 'upstream/github_reports'   # readers' open reports (GitHub issues labelled report), queued first
cd pipeline && uv run dg launch --job agent_recheck --config-json '{"ops": {"recheck": {"config": {"runs": ["<run>"]}}}}'   # check a run's merged facts again; "reviewer": true uses your plan (ADR 0050)
uv run capabilities withdraw reference <route> --citation "<citation>" --reason "<why>" --report <issue>   # take an agent's fact out (or: withdraw ore <mineral>)
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
- `data/`: the graph (quantities, things, verbs, routes, profiles), crosswalks, overrides and suppressions, licensed CC BY-NC-SA 4.0. Things include sources (where a resource is found); extraction routes take materials from them (ADR 0032)
- `examples/jobs/`: feasibility-check jobs; `examples/README.md` holds worked results that tests check
- `packages/core/src/capabilities/`: `graph.py` (the in-memory graph; `Graph.from_curated` reads the YAML), `built.py` (reading the built graph, where its values came from, and occurrences; freshness), `places.py` (where materials and sources are found, for the map), `validate.py`, `tristate.py`, `reasoner.py` (the three questions), `levels.py` (tech levels), `views.py` (display-ready shapes for the web UI, with where values and upstream nodes came from), `withdraw.py` and `yaml_edit.py` (taking agents' facts out of the data as text, ADR 0050), `credits.py` (the works cited in CREDITS.md), `cli.py`
- `packages/api/src/capabilities_api/server.py`: the API under `/api`, which also hosts the web app
- `pipeline/`: `src/capabilities_pipeline/build.py` (loads the curated layer, crosswalks and upstream snapshots into DuckDB, runs dbt, writes the manifest), `upstream.py` (downloading and loading upstream snapshots: MRDS as a zip, Wikidata by a SPARQL query built from the crosswalk, Pleiades as a gzipped CSV, the reference lookups, and readers' reports from GitHub issues), `citations.py` (which works are cited, looking them up in OpenAlex and Crossref, checking links), `agents/` (agents on Claude Code: a task per kind of work, ore crosswalk rows (ADR 0048) and quoted sources for unverified routes (ADR 0049), their checks, gate, draft pull requests and audit log, and re-checking merged facts (ADR 0050)), `assets.py` and `definitions.py` (the same steps as Dagster assets, plus downloads and the `agent_curation` and `agent_recheck` jobs; `[tool.dg]` in `pipeline/pyproject.toml`) and `dbt/` (sources, staging, marts written as Parquet, singular tests in `tests/`). See [ADR 0038](docs/adr/0038-serve-the-app-from-a-built-graph-artifact.md), [ADR 0040](docs/adr/0040-orchestrate-the-build-with-dagster.md), [ADR 0041](docs/adr/0041-place-sources-with-mrds-deposits-through-a-crosswalk.md) and [ADR 0043](docs/adr/0043-take-quantities-from-wikidata-with-upstream-first-and-overrides.md)
- `web/src/`: `api/` (typed client), `graph/` (Cytoscape elements, styles, statuses, tech-tree layout, focus mode, hiding busy nodes' extra lines), `detail/` (detail pane for nodes and lines: route checklists, drill-down, expand-all dialog), `chips/` (node-like chips used in every list), `panes/` (side pane, lists, dialog), `search/`, `lib/bounded.ts` (top N, the rest summarised by type), `map/` (the MapLibre map of where things are found, lazy-loaded), `layout/` (resizable panes), `legend/`, `state/` (selection history and links, explore and explain hooks, breadcrumb trail, theme), `catalog.ts` (labels for any id)
- Tests live beside each package (`packages/*/tests`, `pipeline/tests`); shared fixtures are in the root `conftest.py`
- `snapshots/`: cold backups of every upstream dataset, in git. Every dataset is required; a build uses the newest copy (download or backup) and stops if one has neither ([ADR 0044](docs/adr/0044-require-every-upstream-dataset-with-cold-backups-in-git.md))
- `build/`: generated (upstream snapshots, warehouse, built graph, dbt logs); never commit it
- `docs/`: `architecture/` (overview, data pipeline, technology guides, LikeC4 diagrams), data format, reasoning rules, and ADRs

## Architecture docs

- Every pull request that changes the architecture, the data flow or the technology updates `docs/architecture/` in the same PR ([ADR 0039](docs/adr/0039-keep-architecture-docs-and-diagrams-current.md)): the LikeC4 model and views in `docs/architecture/diagrams/` (new parts go in the `index` view), the overview, the data pipeline reference if data flow changed, and a teaching page under `technologies/` for any new technology (same sections as the others, links to official docs checked to work).
- Model only what exists; planned parts join the diagrams when they are built.
- `cd web && npm run diagrams:check` validates the model; `npm run build` builds it into `web/dist/architecture`, which `capabilities serve` hosts at `/architecture/`.

## Data rules

- **Never invent numbers or citations.** Unknown is fine; guessing is not. Use `basis: unknown` or a `TODO-source` note instead ([ADR 0008](docs/adr/0008-record-the-basis-of-every-number.md)).
- Every route cites at least one reference, with an honest `status` and a `supports` statement. The build checks every cited work against OpenAlex and Crossref ([ADR 0047](docs/adr/0047-check-citations-against-openalex-and-crossref.md)), but a check never changes `status`: only a person who read the work marks it `verified`.
- Know-how never gates a route ([ADR 0005](docs/adr/0005-know-how-never-gates-reachability.md)). Techniques are descriptive labels only.
- Missing data must produce "maybe", never "no" ([ADR 0007](docs/adr/0007-compare-ranges-with-three-answers.md)).
- A natural resource that takes tools to get (timber, quarried stone, mined ore) is `origin: extracted`, with a `source` saying where it is found and a cited extraction route. Only materials gathered by hand as they are stay `origin: natural` ([ADR 0032](docs/adr/0032-extract-materials-from-sources-by-routes.md)).
- The YAML in `data/` is the curated layer; the app reads the graph built from it ([ADR 0034](docs/adr/0034-build-the-graph-from-upstream-datasets-and-a-curated-layer.md), [ADR 0038](docs/adr/0038-serve-the-app-from-a-built-graph-artifact.md)). Every fact must have provenance: curated facts cite references (above); upstream facts carry their dataset and record. Never edit upstream sources, override them in the curated layer instead.
- A quantity value comes from an override, else upstream (Wikidata, for things in `data/crosswalks/wikidata_things.csv`), else the curated YAML ([ADR 0043](docs/adr/0043-take-quantities-from-wikidata-with-upstream-first-and-overrides.md)). To disagree with an upstream value, add an override in `data/overrides/` with a reason and a reference; to leave out an upstream record that doesn't belong, add it to `data/suppressions/suppressed_records.csv` with why. Don't keep a curated value that upstream supplies: remove it, with the references that backed only it ([ADR 0044](docs/adr/0044-require-every-upstream-dataset-with-cold-backups-in-git.md)).
- Ore minerals join the graph through `data/crosswalks/ore_minerals.csv`, one row each with a reference that it was smelted as its class says (and that reference's `status`); a mineral with no such reference stays in the curation queue ([ADR 0045](docs/adr/0045-bring-ore-minerals-in-from-upstream-roast-sulphides-and-queue-the-gaps.md)). Rows agents propose carry `quote` and `proposed_by`, arrive only through draft pull requests, and stay `unverified` until a person reads the work ([ADR 0048](docs/adr/0048-run-agents-through-claude-code-on-a-claude-subscription.md)); so do the references they add to routes, or the quotes they add to a route's references ([ADR 0049](docs/adr/0049-have-agents-quote-sources-for-unverified-routes.md)). A wrong agent fact is withdrawn with `capabilities withdraw`, which removes it and records it in `data/withdrawals.csv`; never put a withdrawn quote back. Readers report facts as GitHub issues (label `report`), queued first; re-checks run only when an admin starts `agent_recheck` ([ADR 0050](docs/adr/0050-report-withdraw-and-recheck-agent-facts.md)). Tests never call `claude`, `gh` or GitHub: use the stand-ins in `pipeline/tests/` and `conftest.py`.
- Crosswalks (`data/crosswalks/*.csv`) match upstream records to our ids. Add a match only when it is defensible and say why in `notes`; leave a source unmapped rather than guess ([ADR 0041](docs/adr/0041-place-sources-with-mrds-deposits-through-a-crosswalk.md)). Pleiades mines and quarries are placed by rules in `pleiades_sources.csv` (a kind of place and a word); a mine that doesn't say which ore belongs to the ore class. Matching needn't be perfect: suppress a wrong match ([ADR 0046](docs/adr/0046-place-ancient-mines-and-quarries-from-pleiades.md)).
- If you change data that the worked examples depend on, update `examples/README.md` and the tests that check it.

## Code conventions

- Python 3.12 with type hints. Keep functions small and named so callers read like prose.
- Comments explain why, not what.
- Tests describe behavior. When a test fails, fix the code unless the test is wrong, and say why.
- Tests must survive data changes: an agent's pull request adds rows and refreshes backups. Work a count or a "top of the queue" out from the data instead of writing it down, name the items a run uses (`names`), and test behaviour that depends on an upstream answer against a fixed recording in `pipeline/tests/fixtures/`, not against `snapshots/`.
- Conventional Commits (`feat:`, `fix:`, `docs:`...), lines under 120 characters.
- Work on a branch and open a draft pull request. Never push to `main`.
- The project is for non-commercial use only: code under PolyForm Noncommercial 1.0.0, data under CC BY-NC-SA 4.0 ([ADR 0037](docs/adr/0037-license-the-project-for-non-commercial-use-only.md)). Check a dependency's or dataset's license before adding it, never call the project "open source", and add every new dataset or cited work to [CREDITS.md](CREDITS.md) (`uv run capabilities credits` regenerates the works cited).
- Web: colours come from CSS custom properties in `web/src/theme.css` (light and dark); the graph reads them, so never hard-code colours in `graph/styles.ts`. A coloured strip with an emoji shows a node's type and its border shows its status ([ADR 0022](docs/adr/0022-type-strip-with-emoji-on-neutral-nodes.md)); status must never rely on colour alone, and nothing may be available only on hover ([ADR 0019](docs/adr/0019-desktop-first-mobile-ready.md)).
