# Architecture overview

Capabilities is a knowledge graph of what it physically takes to make and do things, plus a reasoner that answers three questions about it: what would it take (Q1), what else could a group do (Q2), and could a job have been done a certain way (Q3). This page explains how the pieces fit together. The diagrams are at `/architecture/` when the app is running (see [README](README.md)); the master diagram is the `index` view, and `pipeline_overview` shows the build as a row of stages.

## The big picture

```
 curated layer            pipeline                         built graph              app
 (YAML, CSV in git) ─┐
 data/, schema/      ├▶ loader ──▶ DuckDB ──▶ dbt   ──▶  Parquet + manifest  ──▶  core library ──▶ API server ──▶ browser
 upstream datasets ──┘  (Python)  (warehouse) (models,      (build/graph/)         (reasoner)       (FastAPI)       (React)
 (MRDS, Wikidata,                             tests)
  Pleiades, OpenAlex,
  Crossref; downloaded
  by Dagster)
```

Data flows one way, left to right. People edit the **curated layer**; **upstream datasets** are downloaded as snapshots, and every one is required, with a cold backup of each in git. The **pipeline** turns them into the **built graph**. The **core library** loads the built graph into memory and reasons over it. The **API server** exposes that reasoning as JSON and hosts the **web app**, which draws the graph.

## The parts

| Part | Where | Technology | What it does |
|---|---|---|---|
| Curated layer | `data/`, `examples/jobs/`, `schema/` | [YAML and JSON Schema](technologies/yaml-and-json-schema.md), CSV | The facts people write and review: things, routes, verbs, quantities, profiles and example jobs, one file per node, each checked against a schema; crosswalks, CSV tables matching upstream records to our ids; overrides of upstream values we believe are wrong, with the reason and references; and suppressions of upstream records that don't belong. |
| Upstream datasets | `build/upstream/` (downloaded), `snapshots/` (cold backups, in git) | [Parquet](technologies/parquet.md) | Snapshots of public datasets, each recorded with where and when it was retrieved, its hash and its license. Every dataset is required: a build uses the newest copy, the download or the backup, and stops if one has neither ([ADR 0044](../adr/0044-require-every-upstream-dataset-with-cold-backups-in-git.md)). Today: USGS MRDS mineral deposits ([ADR 0041](../adr/0041-place-sources-with-mrds-deposits-through-a-crosswalk.md)), Wikidata's quantity statements and item descriptions, fetched with [SPARQL](technologies/wikidata-and-sparql.md) ([ADR 0043](../adr/0043-take-quantities-from-wikidata-with-upstream-first-and-overrides.md)), Pleiades' ancient places, a gzipped CSV ([ADR 0046](../adr/0046-place-ancient-mines-and-quarries-from-pleiades.md)), and its time periods, read from Turtle ([ADR 0051](../adr/0051-write-dates-as-signed-years-and-date-workings-from-periods-and-curated-dates.md)), Cliopatria's borders of past polities, a GeoJSON from its latest release ([ADR 0052](../adr/0052-give-profiles-a-cliopatria-place-and-years-and-find-their-sources-on-the-map.md)), Seshat's codings of what polities had, from its API (CC BY-SA, kept to the build, [ADR 0053](../adr/0053-compare-the-graph-with-seshats-codings-of-polities-in-the-build-only.md)), what [OpenAlex and Crossref](technologies/openalex-and-crossref.md) hold for every cited work, with whether each cited link still loads ([ADR 0047](../adr/0047-check-citations-against-openalex-and-crossref.md)), and readers' open reports, from [GitHub issues](technologies/github-issues.md) ([ADR 0050](../adr/0050-report-withdraw-and-recheck-agent-facts.md)). Ore minerals in a hand-kept crosswalk join the graph from them as nodes ([ADR 0045](../adr/0045-bring-ore-minerals-in-from-upstream-roast-sulphides-and-queue-the-gaps.md)). |
| Pipeline | `pipeline/` | [Python](technologies/python-and-uv.md), [DuckDB](technologies/duckdb.md), [dbt](technologies/dbt.md), [Dagster](technologies/dagster.md) | Builds the graph. A Python loader puts every curated document, crosswalk and upstream snapshot into DuckDB tables; a dbt project transforms and tests them, and writes the results as [Parquet](technologies/parquet.md), using [DuckDB's spatial extension](technologies/duckdb-spatial-and-geoparquet.md) for locations. Dagster downloads the upstream snapshots and runs the same steps as assets, with lineage, checks and run history. |
| Agent curation | `pipeline/src/capabilities_pipeline/agents/`, `audit/` (not in git) | [Claude Code agents](technologies/claude-code-agents.md), [Dagster](technologies/dagster.md) | Started by hand: agents on the owner's Claude subscription propose ore crosswalk rows for the curation queue's ore candidates; code checks every source by downloading it, a reviewer agent challenges each proposal, and what passes, built and tested in a temporary worktree, becomes a draft pull request. Every call is in an append-only audit log ([ADR 0048](../adr/0048-run-agents-through-claude-code-on-a-claude-subscription.md)). The same agents quote sources for routes whose references are all unverified ([ADR 0049](../adr/0049-have-agents-quote-sources-for-unverified-routes.md)). An admin can re-check merged facts by run, prompt or model (`agent_recheck`, code's checks free, the reviewer only if asked), and `capabilities withdraw` takes a wrong one out, recorded in `data/withdrawals.csv` ([ADR 0050](../adr/0050-report-withdraw-and-recheck-agent-facts.md)). |
| Built graph | `build/graph/` (generated) | [Parquet](technologies/parquet.md), [GeoParquet](technologies/duckdb-spatial-and-geoparquet.md), JSON | The artifact the app reads: one row per node, where each source kind is found (occurrences, with point geometries), and a manifest saying which inputs it was built from ([ADR 0038](../adr/0038-serve-the-app-from-a-built-graph-artifact.md)). |
| Core library | `packages/core/` | [Python](technologies/python-and-uv.md) | The in-memory graph, the reasoner (Q1–Q3, tech levels, display shapes), where things are found (for the map), the validator, and the `capabilities` command-line tool. |
| API server | `packages/api/` | [FastAPI](technologies/fastapi.md) | JSON endpoints under `/api`, interactive docs at `/docs`, and static hosting for the web app at `/` and these diagrams at `/architecture/`. |
| Web app | `web/` | [React, TypeScript, Vite, Cytoscape.js](technologies/react-vite-and-cytoscape.md), [MapLibre GL JS](technologies/maplibre.md) | The interactive graph, selection panes and detail pane, and a map of where materials and sources are found, over [OpenFreeMap](technologies/maplibre.md) tiles. |
| Architecture docs | `docs/architecture/` | [LikeC4](technologies/likec4.md) | These pages and the diagrams, built into a static site served by the API server. |
| CI | `.github/workflows/ci.yml` | [GitHub Actions](technologies/github-actions.md) | On every pull request: validate the data, build the graph, run every test, lint, type-check and build the web app and diagrams. |

## How a question travels

Take "what else could Middle Kingdom Egypt do?" (Q2) in the browser:

1. **Browser.** Choosing the preset updates the selection. The web app sends `POST /api/explore` with `{"profile": "middle-kingdom-egypt"}`.
2. **API server.** FastAPI validates the request body against a Pydantic model and calls the reasoner. The server loaded the built graph once, at start-up. A profile with a place starts with its list and the sources worked inside its area by its last year, which the build worked out from Cliopatria's borders ([ADR 0052](../adr/0052-give-profiles-a-cliopatria-place-and-years-and-find-their-sources-on-the-map.md)); the answer names those the map added (`from_map`).
3. **Reasoner.** It computes what the selection implies (what it must have needed), what becomes reachable (repeatedly adding everything whose requirements are met until nothing changes, a *fixed point*), and what is one raw ingredient away. Ranges are compared with three answers: yes, no, or maybe ([ADR 0007](../adr/0007-compare-ranges-with-three-answers.md)).
4. **Views.** The result is shaped for display: a status for every node, what implies what, groups for the side panes.
5. **Browser.** The web app colours each node's border by status and lists the results as chips.

**Where it's found** takes a shorter path: `GET /api/occurrences/hematite` returns the places of every source hematite is extracted from, which the server loaded from `source_occurrences.parquet` at start-up, and the web app draws them on a MapLibre map ([ADR 0042](../adr/0042-show-where-things-are-found-on-a-maplibre-map.md)). With a preset that has a place, `?profile=` adds its area and marks which places are inside, and a year control recolours them by whether they were worked by then.

The command line takes the same path without the browser and server: `uv run capabilities explore --profile middle-kingdom-egypt` calls the same reasoner on the same built graph.

## How the graph gets built

`uv run capabilities build` runs the pipeline. The question commands and the server also run it themselves whenever the inputs changed since the last build. Each build:

1. loads every input into raw tables in a DuckDB file: each curated document, whole; each crosswalk and the suppressions; and the newest copy of each upstream dataset, downloaded or backed up. It records a *fingerprint*: a hash of every input (the data, the schemas, the snapshots, and the pipeline's own code);
2. runs `dbt build`: staging views pull typed columns out of each input; one mart chooses each quantity value (an override, else Wikidata's, else the curated one) and writes where it came from to `graph_facts.parquet`; another writes every node, curated and upstream (ore minerals, their deposits and mining routes), with the chosen values, to `graph_nodes.parquet`; a third matches MRDS deposits to our source kinds through the crosswalks, and Pleiades' mines and quarries to our sources and ore classes by rules, dates each (a curated date, else the dataset's), and writes `source_occurrences.parquet`; a fourth checks every cited work against what OpenAlex and Crossref hold, in `reference_checks.parquet`; a fifth lists the gaps it found in `curation_queue.parquet`, the works still to read among them; data tests check the results along the way;
3. writes `manifest.json` last, with that fingerprint. A build is *current* when its fingerprint matches the inputs on disk.

Agents add to the curated layer, never to the built graph: the `agent_curation` job, started by hand, reads the queue and ends in a draft pull request; once a person merges it, the next build includes the rows, each saying which agent run proposed it ([ADR 0048](../adr/0048-run-agents-through-claude-code-on-a-claude-subscription.md)). A reader who finds a fact wrong reports it from the detail pane as a GitHub issue; the next download puts it first in the queue, and a person withdraws or corrects the fact ([ADR 0050](../adr/0050-report-withdraw-and-recheck-agent-facts.md)).

In [Dagster](technologies/dagster.md), the same three steps are assets, along with the download of each upstream snapshot, which only Dagster does: `cd pipeline && uv run dg dev` shows their lineage from the downloads and the YAML to the manifest, runs them, and records every run and check ([ADR 0040](../adr/0040-orchestrate-the-build-with-dagster.md)). The [data pipeline reference](data-pipeline.md) has every detail.

## Key design decisions

The [ADRs](../adr/README.md) record every significant decision. The ones that shape the architecture:

| Decision | ADR |
|---|---|
| The graph is an AND/OR graph: a thing can be made by any of several routes (OR), each needing all of its requirements (AND), with quantity conditions. | [0002](../adr/0002-model-capabilities-as-an-and-or-graph.md) |
| Missing data gives "maybe", never "no". | [0007](../adr/0007-compare-ranges-with-three-answers.md) |
| Python for the reasoner, CLI and server; React and Cytoscape.js for the web. | [0013](../adr/0013-use-python-for-the-reasoner-cli-and-server.md), [0015](../adr/0015-build-the-web-front-end-with-react-and-cytoscape.md) |
| A Python data platform around the graph, deliberately broader than the data needs, as a learning project. | [0033](../adr/0033-build-a-python-data-platform-around-the-graph.md) |
| The graph is a built product: upstream datasets plus a curated layer, every fact with provenance. | [0034](../adr/0034-build-the-graph-from-upstream-datasets-and-a-curated-layer.md) |
| The app reads a built artifact (Parquet and a manifest), rebuilt when its inputs change. | [0038](../adr/0038-serve-the-app-from-a-built-graph-artifact.md) |
| Architecture docs and diagrams are updated with every change. | [0039](../adr/0039-keep-architecture-docs-and-diagrams-current.md) |
| Dagster orchestrates the build as assets; `capabilities build` runs the same steps without it. | [0040](../adr/0040-orchestrate-the-build-with-dagster.md) |
| Sources are placed by occurrences in a geospatial layer, not drawn as graph nodes. | [0036](../adr/0036-place-sources-and-profiles-in-space-and-time.md) |
| MRDS deposits become occurrences of source kinds through a hand-kept crosswalk. | [0041](../adr/0041-place-sources-with-mrds-deposits-through-a-crosswalk.md) |
| A MapLibre map over OpenFreeMap tiles shows where things are found. | [0042](../adr/0042-show-where-things-are-found-on-a-maplibre-map.md) |
| Quantity values come from Wikidata where it has them, over our curated ones; overrides say where we disagree, and the app shows where each value came from. | [0043](../adr/0043-take-quantities-from-wikidata-with-upstream-first-and-overrides.md) |
| Every upstream dataset is required, with a cold backup of each in git; the curated layer doesn't copy upstream values. | [0044](../adr/0044-require-every-upstream-dataset-with-cold-backups-in-git.md) |
| Ore minerals join the graph from upstream through a hand-kept, referenced crosswalk; copper sulphides are roasted; the build keeps a curation queue of the gaps. | [0045](../adr/0045-bring-ore-minerals-in-from-upstream-roast-sulphides-and-queue-the-gaps.md) |
| Pleiades' ancient mines and quarries are placed by rules at our sources, or at an ore class when the ore isn't recorded, with the years they are attested. | [0046](../adr/0046-place-ancient-mines-and-quarries-from-pleiades.md) |
| Years are signed (negative BCE, no year 0). Each occurrence says the year it is known to have been worked by and why: a curated date with references, MRDS's first production, or the end of a Pleiades place's earliest dated period. | [0051](../adr/0051-write-dates-as-signed-years-and-date-workings-from-periods-and-curated-dates.md) |
| The graph is compared with history: a profile is generated for each polity Seshat codes, from its borders and years, and the reasoner's answers are compared with Seshat's codings; every disagreement names what stops it. Seshat's data and the results stay in the build. | [0053](../adr/0053-compare-the-graph-with-seshats-codings-of-polities-in-the-build-only.md) |
| A profile can name a Cliopatria entity and years. Its area is the entity's borders then; a source worked inside it by the profile's last year is had, one only present there is a maybe, and the profile's own list wins. | [0052](../adr/0052-give-profiles-a-cliopatria-place-and-years-and-find-their-sources-on-the-map.md) |
| Every cited work is looked up in OpenAlex and Crossref and every cited link checked; dbt decides the match, and the works still to read form a reading queue. A check never changes a reference's status. | [0047](../adr/0047-check-citations-against-openalex-and-crossref.md) |

## Repository layout

```
schema/              JSON Schemas for every data file type
data/                the curated layer: quantities, things, verbs, routes, profiles, crosswalks, overrides, suppressions
snapshots/           cold backups of the upstream datasets (in git)
examples/            example jobs (Q3) and worked results the tests check
packages/core/       `capabilities`: graph, reasoner, validator, CLI, and their tests
packages/api/        `capabilities_api`: the FastAPI server, and its tests
pipeline/            `capabilities_pipeline`: the build and its Dagster assets (src/), the dbt project (dbt/), and their tests
web/                 the web app; `npm run build` also builds the diagrams into web/dist/architecture
docs/                data format, ADRs, and these architecture docs
build/               generated: upstream snapshots, warehouse, built graph, dbt logs and run folders (not in git)
```

The Python code is a [uv workspace](technologies/python-and-uv.md): three packages in one repository, installed together by `uv sync`. Packages depend on each other, never in a cycle: `api` and `pipeline` depend on `core`, and `core` imports the pipeline only when it needs to rebuild.

## What comes next

The [data platform plan](../adr/0033-build-a-python-data-platform-around-the-graph.md) adds, milestone by milestone: the rest of the upstream datasets (M1), citation checks (M2), AI agents that propose curated facts (M3: ore candidates, sources for unverified routes, and reporting, withdrawing and re-checking facts, done), places and dates for sources and profiles (M4), Apache Iceberg tables with an Apache Polaris catalog (M5), Kubernetes (M6) and Kafka for usage events (M7). Each one updates this page, the diagrams, and adds a technology page.
