# 0040. Orchestrate the build with Dagster, and keep a quick build without it

- **Status:** Proposed
- **Date:** 2026-11-22

## Context

[0033](0033-build-a-python-data-platform-around-the-graph.md) names Dagster as the orchestrator. Milestone 1 adds upstream datasets that have to be downloaded, staged and joined, and later milestones add citation checks and agent runs. These are slow, depend on each other, and need a history of what ran and what it produced.

The graph is already built by `capabilities build` ([0038](0038-serve-the-app-from-a-built-graph-artifact.md)). The question commands and the server use it to rebuild automatically when the inputs change. That rebuild has to stay quick, and it must work with only `uv sync`: no Dagster instance, UI or daemon.

## Decision

We will define the build as **Dagster assets**, and keep `capabilities build` as a way to run the same steps without Dagster.

- **The build is three steps**, each a function in `pipeline/src/capabilities_pipeline/build.py`:
  1. `load_curated` loads the curated documents into DuckDB and records the fingerprint of the inputs it loaded in `raw.loads`.
  2. `dbt build` runs the models and their data tests.
  3. `write_manifest` writes the manifest, using the fingerprint recorded at load time. An edit made during a build therefore leaves the graph stale instead of marking old data as current.
- **Dagster assets** (`assets.py`) wrap these steps. The load is an asset whose key is the dbt source's key, so lineage runs from the YAML through every model. Every dbt model is an asset (dagster-dbt), and every dbt test, on sources and models, is an asset check. The manifest is an asset downstream of `graph_nodes`. Assets are grouped by layer: raw, staging and marts.
- **`capabilities build`** and the automatic rebuild call the same steps directly, in order. Both paths write the same build directory, and a graph built by either one is the graph the app reads.
- **Dagster orchestrates what doesn't belong in a quick rebuild**: downloading upstream snapshots (M1), citation checks (M2) and agent runs (M3). These become assets upstream of the dbt sources, or alongside the marts. A rebuild reads the snapshots already on disk and never downloads anything.
- We use the **`dg` CLI**, configured in `[tool.dg]` in `pipeline/pyproject.toml`, which Dagster's docs now recommend over the `dagster` command. Run history lives in `DAGSTER_HOME`, or in a temporary instance when that is unset.

## Consequences

- Lineage, asset checks and run history for the build in the Dagster UI, with no change to how the app gets its graph.
- One more set of dependencies (Dagster, dagster-dbt, the webserver and `dg`, all Apache-2.0) in the pipeline package, installed by `uv sync`.
- Loading the Dagster definitions runs `dbt parse`, which takes a few seconds, so model changes appear without a separate step.
- Two ways to run the build. They call the same functions, and tests cover both: the build tests, and a test that materializes every Dagster asset and compares the result with the curated graph.
- When the lakehouse arrives (M5), the same assets move to Iceberg storage. The dbt models shouldn't need to change.

## Alternatives considered

- **Dagster only, with `capabilities build` launching a Dagster run.** One path, but every automatic rebuild would pay Dagster's start-up cost and need an instance. Contributors who only edit YAML would gain nothing from that.
- **Keep a plain build and add Dagster later.** Simpler today, but M1's downloads need orchestration, and lineage for the existing models is the easiest place to learn it.
- **Apache Airflow.** The most widely used orchestrator, but it is task-based. Dagster's assets match what we build (tables and files), and its dbt integration gives per-model lineage and checks. Airflow would also need a scheduler and a metadata database to run at all.
- **Prefect.** Pythonic and light, but flow-based rather than asset-based, and its dbt integration is thinner.
- **`DbtProjectComponent` (Dagster's YAML components).** Less code, but it hides the asset definitions we want to learn from, and our load and manifest steps are custom Python anyway.
