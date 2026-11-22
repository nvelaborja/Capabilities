# dbt

## What it is

dbt (data build tool) turns a folder of SQL `select` statements into a tested, documented pipeline of tables and views inside a database. You write each step as a query; dbt works out the order to run them in, creates the tables or views, runs data tests on the results, and records what it did. It handles the **T** in ELT (extract, load, *transform*): data is loaded raw into the database first, then dbt transforms it there.

## How it works

**Models.** A model is one `.sql` file holding one `select`. Its name is the name of the table or view it produces. Models refer to each other with `{{ ref('model_name') }}` instead of a table name. dbt compiles that into the real name, and uses the references to build a dependency graph (a DAG) and run models in order.

**Sources.** Raw tables that dbt didn't create are declared in YAML as *sources* and referred to with `{{ source('raw', 'curated_documents') }}`. That puts them in the lineage graph and lets you test them like models.

**Materializations.** How a model is stored:

| Materialization | Result |
|---|---|
| `view` | A database view; nothing stored, recomputed when queried. |
| `table` | A table, rebuilt on every run. |
| `incremental` | A table that only processes new or changed rows on each run. |
| `ephemeral` | Inlined into the models that use it. |
| `external` | A dbt-duckdb addition: the result is written to a file (Parquet, CSV, JSON) instead of a table. |

**Data tests.** Assertions about the data, declared in YAML beside a model's columns: `unique`, `not_null`, `accepted_values`, `relationships` (every value exists in another model), or any custom SQL query that returns the failing rows. A test passes when it finds no failing rows.

**`dbt build`.** Runs every model, test, seed and snapshot in dependency order. If a test fails, everything downstream of it is skipped, so bad data doesn't flow further.

**Jinja.** SQL files are templates: `{{ ref() }}`, `{{ source() }}`, `{{ config() }}`, `{{ env_var('X') }}`, loops and macros. dbt renders them to plain SQL before running; the compiled SQL is in `target/`.

**Project, profile, adapter.** `dbt_project.yml` holds project settings, such as default materializations per folder. `profiles.yml` holds the connection: which database, and where. An *adapter* teaches dbt a particular database: we use **dbt-duckdb**, so dbt runs our models inside [DuckDB](duckdb.md).

**Layers.** A common convention, which we follow: **staging** models clean and rename one source each (`stg_<source>__<entity>`), and **marts** combine them into what consumers use. This is often described as bronze (raw), silver (staging) and gold (marts), the *medallion* layers.

## How we use it

The dbt project in `pipeline/dbt` turns the raw curated documents into the built graph ([data pipeline](../data-pipeline.md)):

| Layer | Model | Materialization | Does |
|---|---|---|---|
| Source | `raw.curated_documents` | (loaded by Python) | Every YAML document, whole, as JSON. |
| Staging | `stg_curated__documents` | view | Pulls `kind` and `label` out of each document. |
| Mart | `graph_nodes` | external Parquet | Adds provenance; written to `build/graph/graph_nodes.parquet`. |

Tests check that read order and paths are unique, node types are known, kind, label and provenance are present, and ids are unique across every type of node.

The build calls dbt from Python, through `dbtRunner` (dbt's programmatic API), with the target and log paths inside the build directory, so nothing is written into the source tree. dbt's anonymous usage statistics are turned off. [Dagster](dagster.md) runs the same project through dagster-dbt, which turns each model into an asset and each test into an asset check.

Why dbt: transformations become plain SQL with tests and lineage, each new input is one more source and a few models, and it is the standard tool on data platform teams. In M1 it gains seeds (the id crosswalk), more sources (upstream datasets) and more marts. In M9 the same project should run on Databricks.

## Where it lives

| What | Where |
|---|---|
| Project settings | `pipeline/dbt/dbt_project.yml` |
| Connection | `pipeline/dbt/profiles.yml` |
| Sources and their tests | `pipeline/dbt/models/staging/_sources.yml` |
| Staging models and tests | `pipeline/dbt/models/staging/` |
| Marts and tests | `pipeline/dbt/models/marts/` |
| How the build runs dbt | `pipeline/src/capabilities_pipeline/build.py` (`run_dbt`) |
| Compiled SQL, run results, logs | `build/dbt/target/`, `build/dbt/logs/` |

```bash
uv run capabilities build       # loads the raw table, then runs dbt build
# Running dbt directly, after one build has loaded the raw table. dbt resolves relative paths from the
# project directory, so pass absolute ones.
export CAPABILITIES_BUILD_DIR=$PWD/build
uv run dbt build --project-dir pipeline/dbt --profiles-dir pipeline/dbt \
  --target-path "$PWD/build/dbt/target" --log-path "$PWD/build/dbt/logs"
uv run dbt docs generate --project-dir pipeline/dbt --profiles-dir pipeline/dbt \
  --target-path "$PWD/build/dbt/target" --log-path "$PWD/build/dbt/logs"   # the catalog and lineage
```

## Things to know

- One model, one `select`. No `create table` statements: the materialization decides that.
- Always `ref()` and `source()`, never hard-coded table names. Otherwise dbt can't see the dependency.
- Add tests for every assumption a later model or the app relies on.
- Since dbt 1.10, generic test arguments go under `arguments:`, as in `_sources.yml`.

## Further reading

1. [What is dbt?](https://docs.getdbt.com/docs/introduction)
2. [Models](https://docs.getdbt.com/docs/build/models), [Sources](https://docs.getdbt.com/docs/build/sources) and [Materializations](https://docs.getdbt.com/docs/build/materializations).
3. [Data tests](https://docs.getdbt.com/docs/build/data-tests).
4. [How we structure our dbt projects](https://docs.getdbt.com/best-practices/how-we-structure/1-guide-overview): the staging, intermediate and marts convention.
5. [`dbt build`](https://docs.getdbt.com/reference/commands/build), [profiles.yml](https://docs.getdbt.com/docs/core/connect-data-platform/profiles.yml) and [programmatic invocations](https://docs.getdbt.com/reference/programmatic-invocations).
6. [dbt-duckdb](https://github.com/duckdb/dbt-duckdb): the adapter, including external materializations.
7. [Medallion architecture](https://www.databricks.com/glossary/medallion-architecture) (Databricks glossary).
