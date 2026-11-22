# Data pipeline

Reference for how the graph is built: inputs, stages, tables, outputs, checks and commands. The diagram is the `pipeline` view at `/architecture/`. For background on the tools, see [DuckDB](technologies/duckdb.md), [dbt](technologies/dbt.md), [Parquet](technologies/parquet.md) and [Dagster](technologies/dagster.md). Decisions: [ADR 0034](../adr/0034-build-the-graph-from-upstream-datasets-and-a-curated-layer.md) (a built graph from a curated layer and, later, upstream datasets) [ADR 0038](../adr/0038-serve-the-app-from-a-built-graph-artifact.md) (the artifact the app reads) and [ADR 0040](../adr/0040-orchestrate-the-build-with-dagster.md) (Dagster, and the quick build without it).

## Summary

| | |
|---|---|
| **Inputs** | The curated layer: `data/**/*.yaml` (quantities, things, verbs, routes, profiles), `examples/**/*.yaml` (jobs) and `schema/*.json`. No upstream datasets yet (milestone M1). |
| **Output** | `build/graph/graph_nodes.parquet` (one row per node) and `build/graph/manifest.json`. |
| **Run by** | `uv run capabilities build`, or automatically by `need`, `explore`, `check` and `serve` when the output is missing or stale. Or Dagster: the same steps as assets, with lineage, checks and run history (see [Orchestration](#orchestration-dagster)). |
| **Code** | `pipeline/src/capabilities_pipeline/build.py` (extract, load, run dbt, manifest), `assets.py` and `definitions.py` (the same steps as Dagster assets), and `pipeline/dbt/` (the dbt project). Reading: `packages/core/src/capabilities/built.py`. |
| **Engine** | DuckDB, through dbt Core and the dbt-duckdb adapter. |
| **Time** | About 5 seconds with `capabilities build`, most of it dbt starting up; about 20 seconds as a Dagster run, which starts a process per step. |

## Stages

```
data/**/*.yaml ─┐
examples/**/*.yaml ─┤ 1. extract   2. load                3. transform (dbt)                         4. publish
schema/*.json ──┘   (Python)     raw.curated_documents ──▶ stg_curated__documents ──▶ graph_nodes ──▶ graph_nodes.parquet
                                  (DuckDB table)           (view)                     (mart)          manifest.json (last)
```

### 1. Extract

`load_documents(root)` in the core library reads every YAML file under `data/` and `examples/`, in sorted path order, and works out each file's node type from its directory (`routes/` → `route`, `things/` → `thing`, and so on). A YAML syntax error, or a file outside a known directory, stops the build with the file's path. Schema validation is not part of the build: `capabilities validate` does that, and CI runs it before the build.

### 2. Load

Every document goes into the DuckDB warehouse `build/warehouse.duckdb`, whole, as JSON. The fingerprint of the inputs (see [Freshness](#freshness)) is computed just before reading them and recorded beside them. Both tables are replaced on every build.

**`raw.curated_documents`**

| Column | Type | Meaning |
|---|---|---|
| `ordinal` | integer | Position in read order (sorted by path). Kept to the end so the app loads nodes in the same order as the YAML. |
| `node_type` | varchar | `quantity`, `thing`, `verb`, `route`, `profile` or `job`. |
| `id` | varchar | The document's `id`. |
| `document` | json | The whole document. |
| `path` | varchar | The file, relative to the repository root. |

**`raw.loads`**

| Column | Type | Meaning |
|---|---|---|
| `fingerprint` | varchar | The fingerprint of the inputs this load read. The manifest copies it, so an edit made while the build runs leaves the graph stale. |
| `loaded_at` | timestamptz | When the load ran. |

### 3. Transform (dbt)

The build runs `dbt build` on `pipeline/dbt`: `capabilities build` through dbt's Python API, Dagster through dagster-dbt, which runs the dbt command line. `dbt build` runs each model and its tests in dependency order, and stops downstream models when a test fails.

**Source tests** on `raw.curated_documents`: `ordinal` and `path` unique and not null; `node_type` not null and one of the six known types; `id` not null.

**`stg_curated__documents`** (view, `models/staging/`). One row per document, with the fields every node has as columns.

| Column | From |
|---|---|
| `ordinal`, `node_type`, `id`, `document`, `path` | Unchanged from the raw table. |
| `kind` | `document ->> 'kind'` |
| `label` | `document ->> 'label'` |

Tests: `kind` and `label` not null.

**`graph_nodes`** (mart, `models/marts/`, written as Parquet). The built graph.

| Column | Meaning |
|---|---|
| `ordinal` | Read order. |
| `node_type`, `id`, `kind`, `label` | As above. |
| `document` | The full document as JSON: what the app parses. |
| `provenance` | Where the node came from. Today always `{"layer": "curated", "path": "<file>"}`. Upstream records add `{"layer": "upstream", ...}` from M1 (ADR 0034). |

Tests: `ordinal` unique and not null; `id` unique and not null, across every type of node; `provenance` not null.

The mart's `external` materialization (a dbt-duckdb feature) writes the result to `build/graph/graph_nodes.parquet` instead of keeping it as a table in the warehouse.

### 4. Publish

The build counts the rows in the Parquet file and writes **`build/graph/manifest.json`**, with the fingerprint recorded at load time:

| Field | Meaning |
|---|---|
| `format_version` | The artifact's shape (`FORMAT_VERSION` in `built.py`, now 1). Bumping it makes every older build stale. |
| `fingerprint` | SHA-256 over the path and bytes of every input file and of the pipeline's code (below). |
| `built_at` | UTC time of the build. |
| `git_commit` | The commit checked out, if git is available. |
| `tables` | Row count per file, e.g. `{"graph_nodes.parquet": 167}`. |

The manifest is written **last**. If anything fails earlier, no manifest matches the current inputs, so the failed build is never read as current.

## Orchestration (Dagster)

The same steps are Dagster assets ([Dagster](technologies/dagster.md)). `assets.py` defines them, and `definitions.py` is the module Dagster loads, building into the same build directory as `capabilities build`.

| Asset | Group | Step | Checks |
|---|---|---|---|
| `raw/curated_documents` | raw | Load (`load_curated`). Its key is the dbt source's, so lineage runs into dbt. | The source tests above |
| `stg_curated__documents` | staging | dbt view | `kind`, `label` not null |
| `graph_nodes` | marts | dbt mart, written as Parquet | The mart tests above |
| `graph_manifest` | marts | Publish (`write_manifest`) | None |

Every dbt test is an asset check (14 today). Loading the definitions runs `dbt parse` first, so the asset list always matches the dbt project. dbt's files for each Dagster run go in `build/dbt/target/<run>/`.

## Freshness

A build is current when `manifest.json` exists, its `fingerprint` equals the fingerprint of the inputs now, and `graph_nodes.parquet` exists. The fingerprint covers:

- `data/**/*.yaml`, `examples/**/*.yaml` and `schema/*.json` under the repository root;
- the pipeline's code, wherever the pipeline package is installed: `src/capabilities_pipeline/*.py`, `dbt/**/*.sql`, `dbt/**/*.yml`;
- the artifact's `format_version`.

`current_graph()` (used by `need`, `explore`, `check` and the server) rebuilds when the build isn't current, printing a note to stderr, and then loads it. The server loads the graph once at start-up, so restart it after changing data.

## Who reads what

| Reader | Reads | Why |
|---|---|---|
| `need`, `explore`, `check`, `serve` | The built graph (`load_built` via `current_graph`) | They answer questions from what the pipeline built. From M1 this includes upstream data. |
| `validate` | The curated YAML (`Graph.from_curated`) | It checks what people wrote, file by file. |
| `credits` | The curated YAML | The works cited are in the curated layer. |
| Reasoner and view tests | The curated YAML, or small graphs built in the test | Fast, and no build needed. |
| Pipeline and server tests, `test_cli` | A build made once per test run in a temporary directory | They test the real path. |

While the curated layer is the only input, the built graph must equal the curated graph: same documents, same order. `pipeline/tests/test_build.py` checks this, and checks that a worked example gives the same answers from both.

## Files and configuration

| Path | What |
|---|---|
| `build/warehouse.duckdb` | The warehouse: the raw tables and the staging view. |
| `build/graph/` | The artifact the app reads. |
| `build/dbt/target/`, `build/dbt/logs/dbt.log` | dbt's compiled SQL, run results, and log. Dagster runs each get a folder under `target/`. |
| `pipeline/dbt/dbt_project.yml` | Project settings: staging models are views, marts are external Parquet, each layer's Dagster group, and anonymous usage statistics are off. |
| `pipeline/dbt/profiles.yml` | The DuckDB connection: the warehouse path, and `external_root` (where external models are written), both from `$CAPABILITIES_BUILD_DIR`. |
| `pipeline/pyproject.toml`, `[tool.dg]` | Where the `dg` command finds the Dagster definitions. |

The build directory is, in order: `--build-dir`, then `$CAPABILITIES_BUILD_DIR`, then `build/` in the repository. `build/` is ignored by git. Tests always use a temporary directory.

## When a build fails

`BuildError` names the failing models or tests and points to `build/dbt/logs/dbt.log`. Common causes:

- **A data test failed**, for example two nodes share an id. The YAML files can each be valid on their own and still clash. Fix the data and rebuild.
- **A YAML syntax error.** The message names the file.
- **The pipeline package isn't installed** (only the core package was). Run `uv sync` in the repository.

## Commands

```bash
uv run capabilities build                      # build into build/
uv run capabilities --build-dir /tmp/b build   # build somewhere else
uv run capabilities need steel                 # rebuilds first if stale
duckdb build/warehouse.duckdb                  # explore the warehouse (needs the DuckDB CLI)
cd pipeline && uv run dg dev                   # Dagster UI at http://localhost:3000
cd pipeline && uv run dg launch --assets '*'   # a full build as a Dagster run
```

To look at the output from Python:

```python
import duckdb
duckdb.sql("select node_type, count(*) from 'build/graph/graph_nodes.parquet' group by all").show()
```

## Planned changes

| Milestone | Change to the pipeline |
|---|---|
| M1 | Upstream datasets (USGS MRDS, Pleiades, Wikidata) as more raw tables; an id crosswalk as a dbt seed; overrides and suppressions; `source_occurrences` and `curation_queue` marts; Dagster assets that download upstream snapshots. (Dagster already runs the build.) |
| M2 | Citation checks against OpenAlex and Crossref; a `reference_checks` mart. |
| M3 | The agent curation stage and its append-only audit log. |
| M5 | Raw and staging tables move to Apache Iceberg with an Apache Polaris catalog; the build still exports this artifact for the app. |

Each change updates this page in the same pull request ([ADR 0039](../adr/0039-keep-architecture-docs-and-diagrams-current.md)).
