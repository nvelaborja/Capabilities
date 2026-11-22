# Apache Parquet

## What it is

Parquet is an open, columnar file format for tables. Almost every data tool reads and writes it: DuckDB, Spark, Trino, pandas, Polars and every cloud warehouse. It is the usual way to store analytical data in files, and the foundation that table formats like Apache Iceberg build on.

## How it works

**Columns, not rows.** A CSV file stores a table row by row. Parquet stores it column by column, in chunks:

- A file is split into **row groups** (for example a million rows each).
- Inside a row group, each column is a **column chunk**, made of **pages**.
- A **footer** at the end records the schema and, for every column chunk, statistics such as its minimum, maximum and null count.

A reader opens the footer first, then reads only the columns a query needs, and can skip whole row groups whose statistics rule them out. For example, a filter `year > 2000` skips any row group whose maximum year is 1990. This is called *projection* and *predicate pushdown*.

**Typed and compressed.** Every column has a type (integers, strings, timestamps, nested lists and structs), so readers don't guess. Values of one type stored together compress well: repeated strings are dictionary-encoded, and pages are compressed (Snappy or Zstandard).

**Immutable.** You don't update a Parquet file in place; you write a new one. Table formats such as Iceberg (M5) add the missing pieces on top: which files make up a table now, schema changes, and time travel through older versions.

## How we use it

The built graph is `build/graph/graph_nodes.parquet`, written by the dbt mart `graph_nodes` through dbt-duckdb's external materialization, and read by `load_built` ([data pipeline](../data-pipeline.md), [ADR 0038](../../adr/0038-serve-the-app-from-a-built-graph-artifact.md)). It is small today (167 rows), so performance isn't the reason. The reasons are:

- it is the same kind of table the platform will produce at scale, so the app's reader won't change when the data grows;
- every engine we will add can read it;
- you can inspect it with any Parquet tool.

The `document` and `provenance` columns hold JSON, so the app gets each node's full document without the table needing a column per field.

## Where it lives

| What | Where |
|---|---|
| The built graph | `build/graph/graph_nodes.parquet` (generated) |
| How it is written | `pipeline/dbt/dbt_project.yml` (`+materialized: external`, `+format: parquet`) |
| How it is read | `packages/core/src/capabilities/built.py` |

```python
import duckdb
duckdb.sql("describe select * from 'build/graph/graph_nodes.parquet'").show()   # the schema
duckdb.sql("select * from parquet_metadata('build/graph/graph_nodes.parquet')").show()  # row groups and statistics
```

## Things to know

- Order is not guaranteed when a table is read back unless you sort. We keep an `ordinal` column and `order by ordinal` so nodes load in the same order as the YAML.
- Many tiny Parquet files are slow to read; a few large ones are better. This matters for the streaming sink in M7 and for compaction in Iceberg (M5).

## Further reading

1. [Parquet documentation](https://parquet.apache.org/docs/): the overview and concepts.
2. [File format](https://parquet.apache.org/docs/file-format/): row groups, column chunks, pages and metadata in detail.
3. [Parquet in DuckDB](https://duckdb.org/docs/stable/data/parquet/overview): reading, writing and inspecting metadata.
