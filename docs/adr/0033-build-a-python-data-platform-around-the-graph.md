# 0033. Build a Python data platform around the graph

- **Status:** Accepted
- **Date:** 2026-11-20

## Context

The graph is small and written by hand: about 96 things, 53 routes and one profile. Public datasets know far more than we can type: mineral deposits, ancient places, past societies, material properties and the literature. Using them takes ingestion, modelling, quality checks, scheduling and storage that a folder of YAML files can't give.

This is also a learning project. It's acceptable to over-engineer parts of it to gain experience with more technologies, as long as each tool still does a real job here. The platform uses the tools data platform teams commonly use, in the language they mostly use (Python). Keeping today's format and code isn't a constraint.

## Decision

We will build a data platform around the graph, in Python everywhere except the browser.

- **Orchestration: Dagster.** Every dataset, model and output is a Dagster asset, so lineage, schedules, retries and data checks come from one place.
- **Transformation: dbt.** Raw → staging → marts (bronze, silver, gold). dbt tests are the data contracts. Seeds hold small hand-kept tables such as id crosswalks.
- **Storage: Apache Iceberg tables with an Apache Polaris catalog** on S3-compatible storage (SeaweedFS locally, Apache-2.0; MinIO's community edition stopped publishing binaries and images in 2025). It starts as DuckDB with local files and moves to Iceberg once the pipeline works, without rewriting the models. Polaris earns its place by letting more than one engine (DuckDB, Spark, maybe Trino) share the same tables.
- **Streaming: Kafka** carries usage events from the web app, and later pipeline events if useful. It is a learning goal more than a need, and we say so.
- **Deployment: Kubernetes**, locally on a Mac Studio with Helm charts. Docker Compose comes first.
- **Repository: a uv workspace monorepo.** `packages/core` (graph, reasoner, validate), `packages/api` (FastAPI), `pipeline/` (Dagster plus the dbt project), `web/` (React stays: the browser needs JavaScript, and the front end isn't the learning goal), `deploy/`.
- **Databricks is optional and later.** The same dbt project should run there with little change.

The order of the work (milestones M0–M9) lives in the plan, not in this ADR, so it can change without a new ADR. Each choice between engines that needs a trial (the dbt adapter on Iceberg, the local Kubernetes distribution, the schema registry) gets its own ADR after a short spike.

## Consequences

- Running the whole stack needs Docker, and later a local cluster. The core reasoner and CLI must still work with a plain `uv sync`, so contributors and tests don't need the platform.
- The amount of data grows by orders of magnitude, so the app has to read a built graph rather than load YAML files at start-up ([0034](0034-build-the-graph-from-upstream-datasets-and-a-curated-layer.md)).
- Every external dataset needs its license checked against our data license before ingestion ([0037](0037-license-the-project-for-non-commercial-use-only.md)).
- More moving parts to keep running. Each milestone ends with a rebuild from nothing to prove it is reproducible.

## Alternatives considered

- **Keep the scripts and files, and add datasets by hand.** Simplest, but it doesn't scale to thousands of records and teaches none of the target tools.
- **Airflow instead of Dagster.** More widely deployed, but built around tasks rather than data assets. Dagster's asset model and its dbt integration match this pipeline more closely. Either would serve the learning goal.
- **A managed cloud stack from the start (Databricks, Snowflake).** Faster to start, but it hides the catalog, storage and deployment layers this project sets out to learn, and it costs money. Databricks stays as a later comparison.
- **Rewrite the front end in Python (Streamlit, Reflex).** Fewer languages, but it loses the Cytoscape graph work for little learning value.
