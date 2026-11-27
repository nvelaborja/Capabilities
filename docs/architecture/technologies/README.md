# Technologies

One page per technology the project uses. Each page teaches the technology, enough to read and change our code with confidence, and then says exactly how we use it. Every page has the same sections:

- **What it is**: the one-paragraph version.
- **How it works**: the ideas you need, explained from the ground up.
- **How we use it**: what it does in Capabilities, and why we chose it.
- **Where it lives**: the files and commands.
- **Things to know**: gotchas and conventions.
- **Further reading**: official docs and good introductions, in a sensible reading order.

## In use

| Technology | Role | Page |
|---|---|---|
| Python and uv | The language of everything except the browser; uv manages Python, dependencies and the workspace | [python-and-uv.md](python-and-uv.md) |
| YAML and JSON Schema | How the curated data is written and checked | [yaml-and-json-schema.md](yaml-and-json-schema.md) |
| DuckDB | The analytical database the build runs in, and how the app reads the built graph | [duckdb.md](duckdb.md) |
| Apache Parquet | The file format of the built graph | [parquet.md](parquet.md) |
| DuckDB spatial and GeoParquet | Points for where sources are found, profile areas from Cliopatria's borders, and which places are inside them | [duckdb-spatial-and-geoparquet.md](duckdb-spatial-and-geoparquet.md) |
| dbt | Transforms and tests the data inside DuckDB | [dbt.md](dbt.md) |
| Wikidata and SPARQL | Quantity values for our things, from one query to Wikidata | [wikidata-and-sparql.md](wikidata-and-sparql.md) |
| OpenAlex and Crossref | Checking that cited works exist, and finding free copies to read | [openalex-and-crossref.md](openalex-and-crossref.md) |
| Claude Code agents | Agents that propose ore crosswalk rows, on a Claude subscription, checked by code and by each other | [claude-code-agents.md](claude-code-agents.md) |
| GitHub issue forms and the issues API | Readers' reports of wrong facts, and reading them into the curation queue | [github-issues.md](github-issues.md) |
| Dagster | Orchestration: the build as assets, with lineage, checks and run history | [dagster.md](dagster.md) |
| FastAPI | The API server | [fastapi.md](fastapi.md) |
| React, Vite and Cytoscape.js | The web app and the graph drawing | [react-vite-and-cytoscape.md](react-vite-and-cytoscape.md) |
| MapLibre GL JS and OpenFreeMap | The map of where things are found, over OpenStreetMap tiles | [maplibre.md](maplibre.md) |
| LikeC4 | Architecture diagrams as code | [likec4.md](likec4.md) |
| GitHub Actions | Continuous integration | [github-actions.md](github-actions.md) |

## Coming with the data platform

These get a page in the pull request that introduces them ([ADR 0039](../../adr/0039-keep-architecture-docs-and-diagrams-current.md)).

| Technology | Milestone | Role |
|---|---|---|
| Apache Iceberg | M5 | Table format on object storage: snapshots, time travel, schema evolution |
| Apache Polaris | M5 | The Iceberg REST catalog shared by every engine |
| SeaweedFS | M5 | S3-compatible object storage, locally |
| Apache Spark, Trino | M5 | More engines reading the same Iceberg tables |
| Kubernetes and Helm | M6 | Running the platform on a local cluster |
| Apache Kafka (Strimzi) | M7 | Usage events from the web app |
| Databricks | M9 (optional) | Running the same dbt project in a managed platform |
