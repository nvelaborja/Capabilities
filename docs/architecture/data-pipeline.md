# Data pipeline

Reference for how the graph is built: inputs, stages, tables, outputs, checks and commands. The diagram is the `pipeline` view at `/architecture/`. For background on the tools, see [DuckDB](technologies/duckdb.md), [dbt](technologies/dbt.md), [Parquet](technologies/parquet.md) and [Dagster](technologies/dagster.md). Decisions: [ADR 0034](../adr/0034-build-the-graph-from-upstream-datasets-and-a-curated-layer.md) (a built graph from a curated layer and, later, upstream datasets) [ADR 0038](../adr/0038-serve-the-app-from-a-built-graph-artifact.md) (the artifact the app reads), [ADR 0040](../adr/0040-orchestrate-the-build-with-dagster.md) (Dagster, and the quick build without it) and [ADR 0041](../adr/0041-place-sources-with-mrds-deposits-through-a-crosswalk.md) (MRDS deposits as source occurrences). Spatial work uses [DuckDB spatial and GeoParquet](technologies/duckdb-spatial-and-geoparquet.md).

## Summary

| | |
|---|---|
| **Inputs** | The curated layer: `data/**/*.yaml` (quantities, things, verbs, routes, profiles), `data/crosswalks/*.csv`, `examples/**/*.yaml` (jobs) and `schema/*.json`. Upstream snapshots already downloaded into `build/upstream/` (today: USGS MRDS). |
| **Output** | `build/graph/graph_nodes.parquet` (one row per node), `build/graph/source_occurrences.parquet` (where sources are found, GeoParquet) and `build/graph/manifest.json`. |
| **Run by** | `uv run capabilities build`, or automatically by `need`, `explore`, `check` and `serve` when the output is missing or stale. Or Dagster: the same steps as assets, plus downloading upstream snapshots, with lineage, checks and run history (see [Orchestration](#orchestration-dagster)). Only Dagster downloads. |
| **Code** | `pipeline/src/capabilities_pipeline/build.py` (extract, load, run dbt, manifest), `upstream.py` (downloading and loading snapshots), `assets.py` and `definitions.py` (the same steps as Dagster assets), and `pipeline/dbt/` (the dbt project). Reading: `packages/core/src/capabilities/built.py`. |
| **Engine** | DuckDB with its spatial extension, through dbt Core and the dbt-duckdb adapter. |
| **Time** | With the MRDS snapshot, about 8 seconds with `capabilities build` (about 5 without one); about 45 seconds as a Dagster run that downloads MRDS again. |

## Stages

```
                      0. download      1. extract   2. load                    3. transform (dbt)                         4. publish
                      (Dagster only)   (Python)     (DuckDB tables)            (views and marts)
data/**/*.yaml ─┐
examples/**/*.yaml ─┼──────────────────▶ documents ─▶ raw.curated_documents ──▶ stg_curated__documents ──▶ graph_nodes ──▶ graph_nodes.parquet
schema/*.json ──┘
data/crosswalks/*.csv ────────────────────────────▶ raw.mrds_sources ───────────────────────────┐
USGS MRDS ──▶ build/upstream/mrds_deposits/ ─────▶ raw.mrds_deposits ──▶ stg_mrds__deposits ──┴─▶ source_occurrences ──▶ source_occurrences.parquet
              (Parquet + snapshot.json)          raw.upstream_snapshots ──────────────────────┘                          manifest.json (last)
```

### 0. Download (Dagster only)

The `upstream/mrds_deposits` asset downloads `https://mrdata.usgs.gov/mrds/mrds-csv.zip` (about 25 MB, last changed by USGS in 2022), and then:

1. checks that the published columns are the 46 it expects, and fails otherwise, leaving the last snapshot in place;
2. writes every row and column, as text and unchanged, to `build/upstream/mrds_deposits/mrds_deposits.parquet`;
3. writes `snapshot.json` last.

`snapshot.json` records:

| Field | Meaning |
|---|---|
| `url` | Where it was downloaded from. |
| `retrieved_at` | When, in UTC. |
| `last_modified` | The server's `Last-Modified` header. |
| `sha256` | The SHA-256 of the download. |
| `rows` | How many rows it holds. |
| `license` | The dataset's license. |

USGS refuses Python's default user agent, so downloads send a generic one (`dataset-snapshot/1.0`). Nothing in a build downloads: without a snapshot, the load step creates an empty table and the build produces no occurrences.

### 1. Extract

`load_documents(root)` in the core library reads every YAML file under `data/` and `examples/`, in sorted path order, and works out each file's node type from its directory (`routes/` → `route`, `things/` → `thing`, and so on). A YAML syntax error, or a file outside a known directory, stops the build with the file's path. Schema validation is not part of the build: `capabilities validate` does that, and CI runs it before the build.

### 2. Load

`load_inputs` fills the DuckDB warehouse `build/warehouse.duckdb`. It takes the fingerprint of the inputs first (see [Freshness](#freshness)), then loads each kind of input, and records the fingerprint last:

- every curated document, whole, as JSON;
- each crosswalk, as text;
- each upstream snapshot, as text.

Every table is replaced on every build. The crosswalks are loaded here rather than as dbt seeds, because dbt reads seeds only from inside its project ([ADR 0041](../adr/0041-place-sources-with-mrds-deposits-through-a-crosswalk.md)).

**`raw.curated_documents`**

| Column | Type | Meaning |
|---|---|---|
| `ordinal` | integer | Position in read order (sorted by path). Kept to the end so the app loads nodes in the same order as the YAML. |
| `node_type` | varchar | `quantity`, `thing`, `verb`, `route`, `profile` or `job`. |
| `id` | varchar | The document's `id`. |
| `document` | json | The whole document. |
| `path` | varchar | The file, relative to the repository root. |

**`raw.mrds_sources`**: the crosswalk `data/crosswalks/mrds_sources.csv`, every column text: `source_id`, `field` (`ore` or `commodity`), `value`, `deposit_type` (optional), `notes`. See [the data format](../data-format.md#crosswalk-datacrosswalkscsv).

**`raw.mrds_deposits`**: the MRDS snapshot as downloaded, all 46 columns as text (`dep_id`, `site_name`, `latitude`, `longitude`, `country`, `state`, `commod1`–`commod3`, `dep_type`, `dev_stat`, `ore`, `yfp_ba`, `yr_fst_prd`, `score`, `url` and the rest). Empty when nothing has been downloaded.

**`raw.upstream_snapshots`**

| Column | Type | Meaning |
|---|---|---|
| `dataset` | varchar | `mrds_deposits`. |
| `url`, `retrieved_at`, `sha256`, `license` | | From `snapshot.json`. |
| `row_count` | bigint | Rows in the snapshot. |

**`raw.loads`**

| Column | Type | Meaning |
|---|---|---|
| `fingerprint` | varchar | The fingerprint of the inputs this load read. The manifest copies it, so an edit made while the build runs leaves the graph stale. |
| `loaded_at` | timestamptz | When the load ran. |

### 3. Transform (dbt)

The build runs `dbt build` on `pipeline/dbt`: `capabilities build` through dbt's Python API, Dagster through dagster-dbt, which runs the dbt command line. `dbt build` runs each model and its tests in dependency order, and stops downstream models when a test fails.

**Source tests:**

- `raw.curated_documents`: `ordinal` and `path` are unique and not null; `node_type` is not null and one of the six known types; `id` is not null.
- `raw.mrds_sources`: `source_id` is not null and names a curated node; `field` is `ore` or `commodity`; `value` and `notes` are not null.
- `raw.mrds_deposits`: `dep_id` is unique and not null.
- `raw.upstream_snapshots`: `dataset` is unique and not null; `retrieved_at` is not null.

**Singular tests** (`pipeline/dbt/tests/`):

- `crosswalk_maps_to_sources`: every crosswalk row names a source.
- `crosswalk_rows_are_distinct`: no rule is listed twice.
- `stg_mrds_coordinates_are_numbers`: no published coordinate fails to read as a number.
- `occurrences_are_valid_points`: every occurrence is a valid point within latitude ±90 and longitude ±180.

**`stg_curated__documents`** (view, `models/staging/`). One row per document, with the fields every node has as columns.

| Column | From |
|---|---|
| `ordinal`, `node_type`, `id`, `document`, `path` | Unchanged from the raw table. |
| `kind` | `document ->> 'kind'` |
| `label` | `document ->> 'label'` |

Tests: `kind` and `label` not null.

**`stg_mrds__deposits`** (view). One row per MRDS deposit, typed.

| Column | From |
|---|---|
| `record_id`, `name`, `url` | `dep_id`, `site_name`, `url` |
| `latitude`, `longitude` | Read as numbers |
| `country`, `admin_area` | `country`, `state` |
| `development_status`, `deposit_type` | `dev_stat`, `dep_type` |
| `ore_minerals` | `ore`, split at commas into a list |
| `commodities` | `commod1`, `commod2`, `commod3`, split at commas into one list. Names that contain a comma ("Limestone, General") split too, which is harmless: the crosswalk matches whole items. |
| `first_production_year` | `yr_fst_prd`, as an integer |
| `first_production_qualifier` | `yfp_ba`: `before` ("<", production began before that year), `after` (">"), or null |
| `record_quality` | `score`: MRDS's own A–E grade of how much the record holds |

Tests: `record_id` is unique and not null; `first_production_qualifier` is `before`, `after` or null.

**`graph_nodes`** (mart, `models/marts/`, written as Parquet). The built graph.

| Column | Meaning |
|---|---|
| `ordinal` | Read order. |
| `node_type`, `id`, `kind`, `label` | As above. |
| `document` | The full document as JSON: what the app parses. |
| `provenance` | Where the node came from. Today always `{"layer": "curated", "path": "<file>"}`. Upstream records add `{"layer": "upstream", ...}` from M1 (ADR 0034). |

Tests: `ordinal` unique and not null; `id` unique and not null, across every type of node; `provenance` not null.

**`source_occurrences`** (mart, written as GeoParquet). Where each source kind is found ([ADR 0036](../adr/0036-place-sources-and-profiles-in-space-and-time.md)). It has one row per source kind and MRDS deposit, for every deposit with coordinates that matches a crosswalk rule. A deposit that matches two source kinds appears twice.

| Column | Meaning |
|---|---|
| `id` | `<source_id>/mrds/<record_id>`, e.g. `hematite-deposit/mrds/10008106`. |
| `source_id` | The source kind. |
| `dataset`, `record_id` | `mrds`, and the MRDS `dep_id`. |
| `name`, `country`, `admin_area`, `development_status`, `deposit_type`, `ore_minerals`, `commodities`, `record_quality`, `url` | From staging. |
| `geometry` | A point, `ST_Point(longitude, latitude)`, in WGS 84 longitude and latitude (`OGC:CRS84`). |
| `longitude`, `latitude` | The same point as numbers, for readers without a spatial library. |
| `first_production_year`, `first_production_qualifier` | As MRDS gives them. |
| `worked_by_year` | The year by which it is known to have been worked: the first production year, unless production began only "after" it. |
| `state` | `worked` if `worked_by_year` is known, otherwise `present` ("present, not known to be worked by then"). |
| `matched_on` | The crosswalk rule that matched, e.g. `ore: Hematite`. |
| `provenance` | `{"layer": "upstream", "dataset": "mrds", "record": ..., "url": ..., "retrieved_at": ...}`. |

Tests: `id` is unique and not null; `source_id` is not null and names a node in `graph_nodes`; `geometry`, `state` and `provenance` are not null; `state` is `worked` or `present`. Also the valid-points test above.

From the snapshot of 2026-11-22 there are 14,488 occurrences of 8 source kinds: 4,960 for malachite, 4,216 for limestone, 2,655 for hematite, 1,162 for granite, 1,083 for native copper, 238 for diamond gravel, 171 for tin gravel and 3 for flint. Of these, 1,968 have a working year; the earliest is 1505.

The marts' `external` materialization (a dbt-duckdb feature) writes each result to `build/graph/<model>.parquet` instead of keeping it as a table in the warehouse. Two quirks matter to readers of `source_occurrences.parquet` when it is empty (no snapshot):

- dbt-duckdb writes an empty table as **one row of nulls**, so its columns keep their types. Skip rows whose `id` is null; the manifest's counts already do.
- DuckDB writes no GeoParquet metadata for a file with no rows, so `geometry` reads back as WKB bytes. Cast it (`geometry::geometry`) before using spatial functions.

### 4. Publish

The build counts the rows in each Parquet file and writes **`build/graph/manifest.json`**, with the fingerprint recorded at load time:

| Field | Meaning |
|---|---|
| `format_version` | The artifact's shape (`FORMAT_VERSION` in `built.py`, now 2: `source_occurrences.parquet` was added). Bumping it makes every older build stale. |
| `fingerprint` | SHA-256 over the path and bytes of every input file and of the pipeline's code (below). |
| `built_at` | UTC time of the build. |
| `git_commit` | The commit checked out, if git is available. |
| `tables` | Row count per file, e.g. `{"graph_nodes.parquet": 167, "source_occurrences.parquet": 14488}`. |
| `upstream` | The snapshots loaded, by dataset: `url`, `retrieved_at`, `sha256`, `rows`, `license`. Empty when none were downloaded. |

The manifest is written **last**. If anything fails earlier, no manifest matches the current inputs, so the failed build is never read as current.

## Orchestration (Dagster)

The same steps are Dagster assets ([Dagster](technologies/dagster.md)). `assets.py` defines them, and `definitions.py` is the module Dagster loads, building into the same build directory as `capabilities build`.

| Asset | Group | Step | Checks |
|---|---|---|---|
| `upstream/mrds_deposits` | upstream | Download (`fetch` in `upstream.py`). Its URL comes from the `downloads` resource, which tests point at a local file. | None |
| `raw/curated_documents`, `raw/mrds_sources`, `raw/mrds_deposits`, `raw/upstream_snapshots` | raw | Load (`load_inputs`): one multi-asset, since the fingerprint is taken once before anything is read. The keys are the dbt sources' keys, so lineage runs into dbt. | The source tests above |
| `stg_curated__documents`, `stg_mrds__deposits` | staging | dbt views | Their tests above |
| `graph_nodes`, `source_occurrences` | marts | dbt marts, written as Parquet | Their tests above |
| `graph_manifest` | marts | Publish (`write_manifest`) | None |

Every dbt test that belongs to one model or source is an asset check (37 today). Tests that compare two tables, such as `crosswalk_maps_to_sources`, still run in `dbt build` but aren't attached to an asset. "Materialize all" downloads MRDS again; to rebuild from the snapshot you have, select everything except `upstream/mrds_deposits`. Loading the definitions runs `dbt parse` first, so the asset list always matches the dbt project. dbt's files for each Dagster run go in `build/dbt/target/<run>/`.

## Freshness

A build is current when `manifest.json` exists, its `fingerprint` equals the fingerprint of the inputs now, and `graph_nodes.parquet` exists. The fingerprint covers:

- `data/**/*.yaml`, `data/**/*.csv`, `examples/**/*.yaml` and `schema/*.json` under the repository root;
- each upstream snapshot's `snapshot.json` in the build directory, so downloading again makes the graph stale;
- the pipeline's code, wherever the pipeline package is installed: `src/capabilities_pipeline/*.py`, `dbt/**/*.sql`, `dbt/**/*.yml`;
- the artifact's `format_version`.

`current_graph()` (used by `need`, `explore`, `check` and the server) rebuilds when the build isn't current, printing a note to stderr, and then loads it. The server loads the graph once at start-up, so restart it after changing data.

## Who reads what

| Reader | Reads | Why |
|---|---|---|
| `need`, `explore`, `check`, `serve` | The built graph (`load_built` via `current_graph`) | They answer questions from what the pipeline built. From M1 this includes upstream data. |
| `serve`, for the map | `source_occurrences.parquet` (`load_occurrences`) and the manifest's `upstream` | Where each source is found, for `GET /api/occurrences/{id}` ([ADR 0042](../adr/0042-show-where-things-are-found-on-a-maplibre-map.md)). It reads the longitude and latitude columns, so the server needs no spatial extension. |
| `validate` | The curated YAML (`Graph.from_curated`) | It checks what people wrote, file by file. |
| `credits` | The curated YAML | The works cited are in the curated layer. |
| Reasoner and view tests | The curated YAML, or small graphs built in the test | Fast, and no build needed. |
| Pipeline and server tests, `test_cli` | A build made once per test run in a temporary directory | They test the real path. |
| Upstream tests (`pipeline/tests/test_upstream.py`) | A snapshot of 14 real MRDS records (`pipeline/tests/fixtures/mrds-sample.csv`), "downloaded" from a local file | Every crosswalk rule and year rule, with no network. |

While the curated layer is the only source of nodes, the built graph must equal the curated graph: same documents, same order. `pipeline/tests/test_build.py` checks this, and checks that a worked example gives the same answers from both.

## Files and configuration

| Path | What |
|---|---|
| `build/upstream/<dataset>/` | Upstream snapshots: the data as Parquet, and `snapshot.json`. Deleting it means downloading again. |
| `build/warehouse.duckdb` | The warehouse: the raw tables and the staging views. |
| `build/graph/` | The artifact the app reads. |
| `build/dbt/target/`, `build/dbt/logs/dbt.log` | dbt's compiled SQL, run results, and log. Dagster runs each get a folder under `target/`. |
| `pipeline/dbt/dbt_project.yml` | Project settings: staging models are views, marts are external Parquet, each layer's Dagster group, and anonymous usage statistics are off. |
| `pipeline/dbt/profiles.yml` | The DuckDB connection: the warehouse path, and `external_root` (where external models are written), both from `$CAPABILITIES_BUILD_DIR`, and the `spatial` extension. DuckDB downloads the extension the first time it loads it. |
| `pipeline/pyproject.toml`, `[tool.dg]` | Where the `dg` command finds the Dagster definitions. |

The build directory is, in order: `--build-dir`, then `$CAPABILITIES_BUILD_DIR`, then `build/` in the repository. `build/` is ignored by git. Tests always use a temporary directory.

## When a build fails

`BuildError` names the failing models or tests and points to `build/dbt/logs/dbt.log`. Common causes:

- **A data test failed**, for example two nodes share an id. The YAML files can each be valid on their own and still clash. Fix the data and rebuild.
- **A YAML syntax error.** The message names the file.
- **A crosswalk row names something that isn't a source**, or isn't in the graph (`crosswalk_maps_to_sources`, `relationships_...`).
- **The download's columns changed** (Dagster only): USGS changed the file. The last snapshot stays in place; update `MRDS.columns` and the staging model.
- **The pipeline package isn't installed** (only the core package was). Run `uv sync` in the repository.

## Commands

```bash
uv run capabilities build                      # build into build/
uv run capabilities --build-dir /tmp/b build   # build somewhere else
uv run capabilities need steel                 # rebuilds first if stale
duckdb build/warehouse.duckdb                  # explore the warehouse (needs the DuckDB CLI)
cd pipeline && uv run dg dev                   # Dagster UI at http://localhost:3000
cd pipeline && uv run dg launch --assets '*'   # a full build as a Dagster run, downloading MRDS again
cd pipeline && uv run dg launch --assets 'upstream/mrds_deposits'   # just download a new MRDS snapshot
```

To look at the output from Python:

```python
import duckdb
duckdb.sql("select node_type, count(*) from 'build/graph/graph_nodes.parquet' group by all").show()
duckdb.sql("""
    select source_id, state, count(*) from 'build/graph/source_occurrences.parquet'
    where id is not null group by all order by all
""").show()
```

## Planned changes

| Milestone | Change to the pipeline |
|---|---|
| M1 | Done: Dagster runs the build; MRDS, the MRDS crosswalk and `source_occurrences`, served by `GET /api/occurrences/{id}` to the map. Still to come: Pleiades and Wikidata, with a Wikidata crosswalk; overrides and suppressions; upstream nodes in `graph_nodes`; a `curation_queue` mart. |
| M2 | Citation checks against OpenAlex and Crossref; a `reference_checks` mart. |
| M3 | The agent curation stage and its append-only audit log. |
| M5 | Raw and staging tables move to Apache Iceberg with an Apache Polaris catalog; the build still exports this artifact for the app. |

Each change updates this page in the same pull request ([ADR 0039](../adr/0039-keep-architecture-docs-and-diagrams-current.md)).
