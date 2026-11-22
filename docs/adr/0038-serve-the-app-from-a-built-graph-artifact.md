# 0038. Serve the app from a built graph artifact

- **Status:** Proposed
- **Date:** 2026-11-20

## Context

The graph is now a built product ([0034](0034-build-the-graph-from-upstream-datasets-and-a-curated-layer.md)): a pipeline combines the curated layer and, from milestone 1, upstream datasets ([0033](0033-build-a-python-data-platform-around-the-graph.md)). The reasoner, CLI and API server need to read what the pipeline builds, not the YAML files. We had three candidates: an exported file, Postgres, or reading the lakehouse's Iceberg tables directly.

Constraints:
- The reasoner loads the whole graph into memory and needs no queries from a store.
- Contributors and CI must be able to run everything with `uv sync`, with no Docker or running services (0033).
- The app shouldn't stop working because the lakehouse, once it exists, is down or being rebuilt.

## Decision

We will build the graph into a **versioned artifact on disk**, and the app reads that artifact.

- **The artifact is a directory of Parquet tables plus a manifest.** `build/graph/graph_nodes.parquet` has one row per node:
  - its type, id, kind and label;
  - its full document as JSON;
  - its provenance (for now `{"layer": "curated", "path": ...}`);
  - the order it was read in.

  `build/graph/manifest.json` records the artifact format version, a fingerprint of every input (the data, the schemas, and the pipeline's code and dbt project), the build time, the git commit, and row counts.
- **dbt builds it.** `capabilities build` loads every curated document, whole, into a raw DuckDB table. A dbt project (`pipeline/dbt`) then turns it into a staging view and the `graph_nodes` mart, written as Parquet by dbt-duckdb. dbt data tests guard the build, for example ids unique across every type of node. Parsing and joining are dbt's job, so new inputs arrive as raw tables and models, not more Python.
- **Reading is explicit.** `Graph.from_curated` reads the YAML (for `validate`, tests, and as the build's input). `capabilities.built` reads the artifact. `need`, `explore`, `check` and the server read the built graph and rebuild it first when its fingerprint no longer matches the inputs, saying so.
- **The built graph must equal the curated graph** while the curated layer is its only input. A test compares every node and the order they were read in, and the answers to a worked example.
- **Later stores feed the same artifact.** When the lakehouse arrives (milestone 5), the marts live in Iceberg, and the build still exports this artifact for the app. Postgres or direct Iceberg reads get their own ADR if the app ever needs queries the artifact can't answer.

## Consequences

- One `uv sync` installs dbt and DuckDB. The first question after a data change takes a few seconds while it rebuilds; after that it's as fast as before.
- The repository's `build/` directory holds the warehouse, the artifact and dbt's logs. It is ignored by git, and tests build into a temporary directory instead.
- A failed build never looks current: the manifest is written last, and only after dbt's tests pass.
- The artifact is easy to inspect with any Parquet tool, and DuckDB can query it directly.
- Two ways to load a graph means two code paths. The equality test keeps them identical until upstream data makes them differ on purpose.

## Alternatives considered

- **Keep loading YAML in the app, and use the pipeline only for analysis.** Simplest, but upstream data would never reach the app.
- **Postgres.** A real query engine and a familiar service, but another server to run for every contributor and test, for an app that loads everything into memory anyway.
- **Read Iceberg directly from the app.** One copy of the data, but the app would depend on the catalog and object storage being up, and Iceberg doesn't exist until milestone 5.
- **One JSON file.** Simple to read, but it doesn't match the tables the pipeline produces, and DuckDB and dbt can't write or test it as naturally as Parquet.
