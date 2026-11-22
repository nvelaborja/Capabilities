# Dagster

## What it is

Dagster is an orchestrator: it runs the steps of a data pipeline in the right order, records every run, and shows what each piece of data was made from and whether it is up to date. Where older orchestrators (such as Apache Airflow) think in *tasks* ("run this script, then that one"), Dagster thinks in *assets*: the tables, files and models the pipeline produces. You declare each asset and what it depends on; Dagster works out the order, runs them, and keeps a history of every materialization.

## How it works

**Assets.** An asset is a piece of data that should exist, plus the function that makes it. In Python, it is a function decorated with `@asset`; its *key* (such as `raw/curated_documents`) names the data, and its `deps` name the assets it reads. *Materializing* an asset means running its function to (re)create the data. Each materialization is recorded with metadata the function returns, such as a row count.

**The asset graph.** Dependencies between assets form a directed acyclic graph (DAG). Dagster draws it as *lineage*: for any asset you can see what it was built from and what is built from it. Materializing a selection of assets runs them in dependency order.

**Groups.** Assets are put in named groups, shown together in the UI. We group ours by layer: `upstream`, `raw`, `staging`, `marts`.

**Multi-assets.** One function that materializes several assets at once, declared with `@multi_asset(specs=[AssetSpec(...), ...])` and yielding a `MaterializeResult` per asset. Use one when several assets must be produced together, such as tables loaded in a single step.

**Asset checks.** Tests attached to an asset, run after it is materialized, with a pass or fail result recorded next to the materialization. With dbt, every data test becomes an asset check.

**Resources.** Connections and clients an asset needs (a database, an API client, the dbt command line), given to asset functions as parameters. Swapping a resource (local DuckDB for a cloud warehouse) doesn't change the assets. A `ConfigurableResource` is a class whose fields are its settings, which is how tests point a download at a local file.

**Definitions.** One `Definitions` object collects the assets, checks, resources, schedules and sensors of a *code location*. Dagster loads it from a Python module.

**Runs, schedules and sensors.** A *run* is one execution of a selection of assets, with its logs and events. A *schedule* starts runs at set times; a *sensor* starts them when something happens (a new file, another asset updating). We don't use either yet.

**The UI and the `dg` command.** `dg dev` starts a local Dagster instance: the web UI (lineage, runs, checks, logs) plus the processes that load code and run it. `dg launch` runs a selection of assets from the command line. `dg` reads its settings from `[tool.dg]` in `pyproject.toml`. The older `dagster` command still works, but the docs now recommend `dg`.

**The instance.** Run history, event logs and schedules are stored in the *instance*, a directory named by the `DAGSTER_HOME` environment variable. If it isn't set, `dg dev` makes a temporary one (`.tmp_dagster_home_*` in the folder it runs in, ignored by git), so run history doesn't carry over to the next session.

**dagster-dbt.** The dbt integration reads a dbt project's `manifest.json` and turns every model into an asset, every source into an upstream asset key, and every data test into an asset check. One function decorated with `@dbt_assets` runs `dbt build` for whichever models are selected and streams dbt's results back as Dagster events.

## How we use it

`pipeline/src/capabilities_pipeline/` defines the build as assets:

| Asset | Group | Made by | What it is |
|---|---|---|---|
| `upstream/mrds_deposits` | upstream | Python (`fetch` in `upstream.py`) | A snapshot of USGS MRDS: downloaded, checked, converted to Parquet unchanged, recorded in `snapshot.json`. |
| `raw/curated_documents`, `raw/mrds_sources`, `raw/mrds_deposits`, `raw/upstream_snapshots` | raw | Python (`load_inputs`), one multi-asset | The curated documents, the MRDS crosswalk and the MRDS snapshot loaded into DuckDB, with the fingerprint of the inputs in `raw.loads`. Their keys are the dbt sources' keys, so lineage runs straight into dbt. |
| `stg_curated__documents`, `stg_mrds__deposits` | staging | dbt (views) | Typed columns pulled out of each input. |
| `graph_nodes` | marts | dbt (external Parquet) | The built graph's nodes, with provenance. |
| `source_occurrences` | marts | dbt (external GeoParquet) | Where each source kind is found, from MRDS and the crosswalk. |
| `graph_manifest` | marts | Python (`write_manifest`) | `build/graph/manifest.json`: what the graph was built from. |

Every dbt data test on one source or model is an asset check (37 today). The dbt models' groups come from `+meta: {dagster: {group: ...}}` in `dbt_project.yml`. The download's URL comes from the `downloads` resource (`UpstreamDownloads`), which the tests point at a zip of 14 real records.

There are two ways to run the build, and they run the same three steps:

- **`capabilities build`**, and the automatic rebuild when a question or the server finds the graph stale, call `build()` in `build.py` directly. Rebuilding is fast and needs no Dagster instance.
- **Dagster** runs them as assets, with lineage, checks and a history of runs, and also does what doesn't belong in a quick rebuild: downloading upstream datasets now, and citation checks and agent runs later. A quick rebuild uses whatever snapshots Dagster downloaded last.

Why Dagster: its asset model matches what we build (tables and files, not tasks), the dbt integration gives per-model lineage and checks for free, and it is widely used on data platform teams ([ADR 0033](../../adr/0033-build-a-python-data-platform-around-the-graph.md), [ADR 0040](../../adr/0040-orchestrate-the-build-with-dagster.md)).

## Where it lives

| What | Where |
|---|---|
| The assets | `pipeline/src/capabilities_pipeline/assets.py` (`definitions(root, build_dir)`) |
| What Dagster loads | `pipeline/src/capabilities_pipeline/definitions.py` (`defs`) |
| The steps both paths share | `pipeline/src/capabilities_pipeline/build.py` |
| Downloading and loading snapshots | `pipeline/src/capabilities_pipeline/upstream.py` |
| `dg` settings | `[tool.dg]` in `pipeline/pyproject.toml` |
| dbt's files for each Dagster run | `build/dbt/target/<run>/` |
| Tests | `pipeline/tests/test_assets.py` |

```bash
cd pipeline
uv run dg dev                          # the UI at http://localhost:3000: Lineage, then "Materialize all"
uv run dg launch --assets '*'          # one full build from the command line, downloading MRDS again
uv run dg launch --assets 'upstream/mrds_deposits'   # just a new MRDS snapshot
uv run dg list defs                    # the assets, checks and resources Dagster sees
DAGSTER_HOME=$PWD/../build/dagster uv run dg dev   # keep run history between sessions (create the folder first)
```

## Things to know

- Run `dg` from `pipeline/`, where its `[tool.dg]` settings are.
- Loading the definitions runs `dbt parse` (a few seconds), so a new or renamed dbt model appears without a separate step. Use **Reload definitions** in the UI after changing code.
- Don't add `from __future__ import annotations` to a module with Dagster assets: Dagster reads the `context` parameter's type when it loads them, and that import turns types into strings.
- Assets build into `build/` (or `$CAPABILITIES_BUILD_DIR`), the same place as `capabilities build`, so a graph built in Dagster is the one the app reads.
- "Materialize all" includes the download. To rebuild from the snapshot you already have, select the raw, staging and marts groups instead.
- A dbt test that compares two tables (a *singular* test such as `crosswalk_maps_to_sources`) runs in every `dbt build` but isn't shown as a check, because it belongs to no single asset.
- The UI's browser console logs some Apollo cache errors. They come from Dagster's own UI, not from our code.

## Further reading

1. [Dagster documentation](https://dagster.io/docs): start with the quickstart and "Assets".
2. [Defining assets](https://dagster.io/docs/guides/build/assets/defining-assets) and [asset checks](https://dagster.io/docs/guides/test/asset-checks).
3. [dbt integration](https://dagster.io/docs/integrations/libraries/dbt): how dbt models, sources and tests become assets and checks.
4. [The `dg` CLI](https://dagster.io/docs/api/clis/dg-cli/dg-cli-reference).
5. [What are software-defined assets?](https://dagster.io/blog/software-defined-assets) (Dagster blog): why assets instead of tasks.
