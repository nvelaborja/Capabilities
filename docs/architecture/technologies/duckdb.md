# DuckDB

## What it is

DuckDB is an analytical SQL database that runs *inside* your program, like SQLite, but built for analysis: scanning, filtering, joining and aggregating many rows at once. There is no server to start. A database is a single file, or just memory, and DuckDB can query files such as Parquet, CSV and JSON directly, without loading them first.

## How it works

**In-process.** You `import duckdb` (or run the `duckdb` command-line tool) and the whole engine runs in your process. Nothing to install as a service or connect to over a network, which is why it suits a local build and tests.

**Columnar and vectorized.** Analytical databases (OLAP) store and process data by column rather than by row. A query that reads three columns out of fifty reads only those three, and values of the same type sit together, so they compress well. DuckDB also processes data in *vectors*, batches of about two thousand values at a time, which keeps the CPU busy and is much faster than handling one row at a time. Transactional databases such as Postgres (OLTP) make the opposite trade: fast single-row inserts and updates.

**SQL on files.** `select * from 'build/graph/graph_nodes.parquet'` works as is. DuckDB reads the file's metadata, reads only the columns and row groups it needs, and can write results back out with `copy ... to 'file.parquet'`. This is what makes it a natural engine for a *lakehouse*, where data lives in open file formats rather than inside one database.

**JSON.** The JSON extension adds a `json` type and operators: `document ->> 'kind'` extracts a field as text, `document -> 'requires'` as JSON. It lets us keep whole documents as JSON and pull fields out in SQL.

**Python API.** `duckdb.sql("...")` returns a *relation*: a query description that runs when you ask for results (`.fetchall()`, `.show()`, `.df()`). `duckdb.connect("file.duckdb")` opens a persistent database. Parameters are passed separately (`params=[...]`), never pasted into the SQL.

## How we use it

- **The build's warehouse.** The pipeline loads every curated document, crosswalk and upstream snapshot into raw tables in `build/warehouse.duckdb`, and [dbt](dbt.md) runs its models there ([data pipeline](../data-pipeline.md)).
- **Converting downloads.** An upstream CSV is read with `read_csv(..., all_varchar = true)` and written to Parquet unchanged.
- **Writing the built graph.** dbt-duckdb writes the `graph_nodes` and `source_occurrences` marts as [Parquet](parquet.md) files.
- **Geometry.** The spatial extension makes the occurrences' points and writes them as GeoParquet ([DuckDB spatial and GeoParquet](duckdb-spatial-and-geoparquet.md)).
- **Reading the built graph.** `capabilities.built.load_built` reads `graph_nodes.parquet` with one DuckDB query and parses each document.

Why DuckDB: no server, so `uv sync` is enough for contributors and CI ([ADR 0033](../../adr/0033-build-a-python-data-platform-around-the-graph.md)); it is fast; and it is one of the engines that will read the same Iceberg tables in M5.

## Where it lives

| What | Where |
|---|---|
| Loading raw tables | `pipeline/src/capabilities_pipeline/build.py` (`load_inputs`) and `upstream.py` (`load_upstream`) |
| Connection for dbt | `pipeline/dbt/profiles.yml` |
| Reading the artifact | `packages/core/src/capabilities/built.py` (`load_built`) |
| The warehouse file | `build/warehouse.duckdb` (generated) |

```python
import duckdb
duckdb.sql("select node_type, count(*) as nodes from 'build/graph/graph_nodes.parquet' group by all").show()
with duckdb.connect("build/warehouse.duckdb", read_only=True) as con:
    con.sql("select id, kind, label from stg_curated__documents limit 5").show()
```

## Things to know

- DuckDB 2.0 changed the Python relation API: a relation keeps no result between calls, so `fetchone()` is gone. Use `fetchall()`.
- DuckDB 2.0 also changed lambdas: `list_transform(items, lambda x: trim(x))`. The old arrow form (`x -> trim(x)`) is an error.
- Comma-separated values in a text column become a list with `string_split(text, ',')`; `list_contains`, `list_filter` and `list_transform` then work on it.
- Only one process can open a database file for writing at a time. Close connections (`with duckdb.connect(...)`) before dbt runs.
- `group by all` and `select * exclude (col)` are DuckDB conveniences, not standard SQL.

## Further reading

1. [Why DuckDB](https://duckdb.org/why_duckdb): what it is for and how it differs from other databases.
2. [SQL introduction](https://duckdb.org/docs/stable/sql/introduction) in the DuckDB docs.
3. [Python API overview](https://duckdb.org/docs/stable/clients/python/overview).
4. [Reading and writing Parquet](https://duckdb.org/docs/stable/data/parquet/overview) and [JSON](https://duckdb.org/docs/stable/data/json/overview).
5. [DuckDB documentation](https://duckdb.org/docs/stable/): everything else.
