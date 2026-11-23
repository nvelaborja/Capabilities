# 0041. Place sources with MRDS deposits, matched through a hand-kept crosswalk

- **Status:** Accepted
- **Date:** 2026-11-22

## Context

Sources ([0032](0032-extract-materials-from-sources-by-routes.md)) are kinds, such as "hematite deposit", and [0036](0036-place-sources-and-profiles-in-space-and-time.md) gives each kind **occurrences**: located places, each with its upstream record and, where known, when it was first worked. The USGS Mineral Resources Data System (MRDS, US public domain) is the first dataset to provide them: 304,632 deposits worldwide, most in the United States, each with coordinates, its ore minerals, its commodities, a deposit type and, for some, a year of first production.

MRDS has no ids for our source kinds. Its `ore` field lists mineral names ("Hematite, Malachite, Pyrite"). Its commodity fields list commodity names, and some of those contain a comma themselves ("Limestone, General"). Some source kinds are narrower than a mineral: tin gravel is cassiterite in a placer, not in a vein. Others, such as bog iron, have no structured field to match on at all.

[0034](0034-build-the-graph-from-upstream-datasets-and-a-curated-layer.md) says a hand-kept crosswalk maps our ids to upstream ids, and [0033](0033-build-a-python-data-platform-around-the-graph.md) suggests dbt seeds for it. [0040](0040-orchestrate-the-build-with-dagster.md) says only Dagster downloads, and a rebuild must work with only `uv sync` and no network.

## Decision

**The crosswalk.**
- It is a CSV file in the curated layer, `data/crosswalks/mrds_sources.csv`. Each row has a source kind, a field (`ore` or `commodity`), the MRDS value to match, an optional deposit type, and a note saying why the match holds.
- A deposit is an occurrence of a source kind when the field's list includes the value (ignoring case) and, if a deposit type is given, the deposit's type contains it.
- A deposit can match several source kinds. It is then an occurrence of each, so a deposit listing hematite and malachite appears under both.
- Lists are split at every comma, so "Limestone, General" becomes two items, "Limestone" and "General", and the crosswalk matches "Limestone". This is harmless because the crosswalk only matches whole items.
- Source kinds with no defensible match stay unmapped. These are bog iron, dolerite and standing trees. They are curation work (M1 slice 4's queue), and we never guess a match.

**Loading the crosswalk.**
- The build loads it in Python, into a raw table, as text exactly as written, like the curated YAML. It is not a dbt seed.
- A build reads its inputs from a root directory, and dbt reads seeds only from paths relative to its own project. An absolute seed path made dbt write the seed's compiled SQL over the CSV itself, because it saves run files under `target/run/<project>/<seed path>`.
- dbt still tests the crosswalk:
  - every row names a node, and that node is a source;
  - each rule is listed once;
  - the field is one of the two allowed values.

**Snapshots.**
- A Dagster asset (`upstream/mrds_deposits`) downloads `mrds-csv.zip`. It converts the CSV to Parquet with every column kept as text, and checks that the published columns haven't changed. It writes `snapshot.json` last, with the URL, retrieval time, SHA-256 of the download, row count and license.
- Snapshots live in the build directory (`build/upstream/<dataset>/`).
- The build's fingerprint includes each `snapshot.json`, so a new download makes the graph stale. The manifest records the snapshots the graph was built from.
- A build without a snapshot loads an empty table and produces no occurrences, so CI and a fresh clone still build with no network.

**The `source_occurrences` mart.**
- It is written to `build/graph/source_occurrences.parquet` as GeoParquet, with one row per source kind and deposit.
- Each row has a point geometry made with DuckDB's spatial extension, plus the deposit's name, country, development status, deposit type, and ore minerals and commodities.
- Its provenance is upstream: the dataset, the record id, the record's URL, and when the snapshot was retrieved.
- Deposits without coordinates are left out, because they can't be placed.

**When a deposit counts as worked.**
- MRDS gives a year of first production. A qualifier can say that production began before that year ("<") or after it (">").
- `worked_by_year` is the year by which the deposit is known to have been worked: the first production year, unless the qualifier says "after".
- `state` is `worked` when that year is known, and otherwise `present`. `present` is [0036](0036-place-sources-and-profiles-in-space-and-time.md)'s "present, not known to be worked by then". We call it `present` rather than "not worked" because a mine whose production years are unknown has still been worked.
- Suppressed records come with overrides and suppressions (M1 slice 4).

**Changes to the build steps.** The load step that [0040](0040-orchestrate-the-build-with-dagster.md) calls `load_curated` is now `load_inputs`. It loads the curated documents, the crosswalks and the upstream snapshots, in that order, after taking the fingerprint. In Dagster it is one multi-asset with a raw table for each input.

## Consequences

- The first upstream facts reach the build. With the snapshot of 2026-11-22, the build has 14,488 occurrences of 8 source kinds:
  - 4,960 for malachite, 4,216 for limestone, 2,655 for hematite, 1,162 for granite, 1,083 for native copper, 238 for diamond gravel, 171 for tin gravel and 3 for flint;
  - 1,968 of them with a known working year, the earliest 1505.
- These are modern records, mostly American. The map (M1 slice 3) will show where a resource exists, and very little about antiquity. Ancient working dates come from curation and agents ([0035](0035-propose-curated-facts-with-audited-agents.md)), as 0036 expected.
- A rebuild with MRDS takes about 8 seconds instead of about 5.
- The spatial extension is downloaded by DuckDB the first time it is loaded, and cached after that. The first build on a new machine needs the network once.
- DuckDB writes no GeoParquet metadata for a file with no rows, and dbt-duckdb writes an empty table as one row of nulls. Readers of `source_occurrences.parquet` skip rows whose `id` is null, and cast `geometry` to a geometry.
- The crosswalk's quality decides the map's quality. Each row carries its reasoning, and changes are reviewed in pull requests like any curated fact.

## Alternatives considered

- **A dbt seed for the crosswalk.** This is the usual dbt pattern, and ADR 0033 suggests it. But seeds must live inside the dbt project, which would separate the crosswalk from the rest of the curated layer and from the root a build reads. A path outside the project overwrote the seed (above).
- **Match on mineral alone, mapping our materials to MRDS minerals and reaching sources through extraction routes.** No new table, but tin gravel would include every cassiterite vein, and diamond gravel every kimberlite pipe. Matching by source kind lets a row narrow by deposit type.
- **Match on site names ("Bog Iron Deposit").** It would place bog iron, but names are free text. A rule on them is a guess, and the curation queue is the place for those records.
- **Keep snapshots in git, or outside the build directory.** The snapshot is 32 MB of Parquet from a 25 MB download, and it is reproducible from the URL and hash. Deleting `build/` means downloading again, and that is cheap.
- **The full relational MRDS download (`rdbms-tab-all.zip`, one table per topic).** It has cleaner lists, with one row per commodity and per mineral, but it is 124 MB and more tables to stage. The single CSV covers every field we use. We can switch later without changing the mart.
- **Mark a deposit worked whenever MRDS says it produced ("Producer", "Past Producer").** That would say it was worked, but not by when. Availability for a profile needs a date ([0036](0036-place-sources-and-profiles-in-space-and-time.md)), so without one the deposit is `present`, and its development status is shown alongside.
