# Data pipeline

Reference for how the graph is built: inputs, stages, tables, outputs, checks and commands. The diagrams are at `/architecture/`: `pipeline_overview` shows the build as stages in series (1a curated layer and 1b download, 2 load, 3a transform and 3b test, 4 publish, 5 serve), and `pipeline` shows every input, table and output in the same stages, with green lineage arrows for where the data goes next. For background on the tools, see [DuckDB](technologies/duckdb.md), [dbt](technologies/dbt.md), [Parquet](technologies/parquet.md) and [Dagster](technologies/dagster.md). Decisions: [ADR 0034](../adr/0034-build-the-graph-from-upstream-datasets-and-a-curated-layer.md) (a built graph from a curated layer and, later, upstream datasets) [ADR 0038](../adr/0038-serve-the-app-from-a-built-graph-artifact.md) (the artifact the app reads), [ADR 0040](../adr/0040-orchestrate-the-build-with-dagster.md) (Dagster, and the quick build without it), [ADR 0041](../adr/0041-place-sources-with-mrds-deposits-through-a-crosswalk.md) (MRDS deposits as source occurrences) [ADR 0043](../adr/0043-take-quantities-from-wikidata-with-upstream-first-and-overrides.md) (quantities from Wikidata, upstream first, with overrides) [ADR 0044](../adr/0044-require-every-upstream-dataset-with-cold-backups-in-git.md) (every dataset required, with cold backups in git) [ADR 0045](../adr/0045-bring-ore-minerals-in-from-upstream-roast-sulphides-and-queue-the-gaps.md) (ore minerals from upstream as nodes, and the curation queue) [ADR 0048](../adr/0048-run-agents-through-claude-code-on-a-claude-subscription.md) (agents proposing ore crosswalk rows) and [ADR 0049](../adr/0049-have-agents-quote-sources-for-unverified-routes.md) (agents quoting sources for unverified routes). Spatial work uses [DuckDB spatial and GeoParquet](technologies/duckdb-spatial-and-geoparquet.md); Wikidata is queried with [SPARQL](technologies/wikidata-and-sparql.md).

## Summary

| | |
|---|---|
| **Inputs** | The curated layer: `data/**/*.yaml` (quantities, things, verbs, routes, profiles, overrides), `data/crosswalks/*.csv`, `data/suppressions/*.csv`, `examples/**/*.yaml` (jobs) and `schema/*.json`. A copy of every upstream dataset (USGS MRDS, Wikidata's quantity statements and item descriptions, Pleiades' places, what OpenAlex and Crossref hold for each cited work, and readers' open reports from GitHub issues): the latest download in `build/upstream/` or the cold backup in `snapshots/`, whichever is newer. Every dataset is required ([ADR 0044](../adr/0044-require-every-upstream-dataset-with-cold-backups-in-git.md)). |
| **Output** | `build/graph/graph_nodes.parquet` (one row per node), `build/graph/graph_facts.parquet` (where each quantity value comes from), `build/graph/source_occurrences.parquet` (where sources are found, GeoParquet), `build/graph/curation_queue.parquet` (the gaps the build found), `build/graph/reference_checks.parquet` (each cited work checked against OpenAlex and Crossref) and `build/graph/manifest.json`. |
| **Run by** | `uv run capabilities build`, or automatically by `need`, `explore`, `check` and `serve` when the output is missing or stale. Or Dagster: the same steps as assets, plus downloading upstream snapshots, with lineage, checks and run history (see [Orchestration](#orchestration-dagster)). Only Dagster downloads. |
| **Code** | `pipeline/src/capabilities_pipeline/build.py` (extract, load, run dbt, manifest), `upstream.py` (downloading and loading snapshots), `citations.py` (looking up cited works and checking links), `assets.py` and `definitions.py` (the same steps as Dagster assets), and `pipeline/dbt/` (the dbt project). Reading: `packages/core/src/capabilities/built.py`. |
| **Engine** | DuckDB with its spatial extension, through dbt Core and the dbt-duckdb adapter. |
| **Time** | About 7 seconds with `capabilities build`; about 45 seconds as a Dagster run that downloads MRDS again. The Wikidata query takes under a second; looking up the cited works about a minute and a half, mostly Crossref's limit of one search a second. |

## Stages

Numbered as in the `pipeline_overview` diagram. 1a and 1b feed 2 side by side; 3a and 3b are a pair, since `dbt build` tests each model right after building it; 5, serving, is under [Who reads what](#who-reads-what).

```
                     1b. download     1a. extract  2. load                       3a/3b. transform and test (dbt)                 4. publish
                     (Dagster only)   (Python)     (DuckDB tables)               (views and marts)
data/**/*.yaml ─────┐
examples/**/*.yaml ─┼────────────────▶ documents ─▶ raw.curated_documents ──▶ stg_curated__documents ─────────────────▶ graph_nodes ──▶ graph_nodes.parquet
schema/*.json ──────┘                                                         stg_curated__quantities,                        ▲
                                                                              __overrides, __quantity_properties ──┐          │
data/crosswalks/wikidata_things.csv ─────────────▶ raw.wikidata_things ────────────────────────────────────────────┤          │
Wikidata ──▶ build/upstream/wikidata_quantities/ ▶ raw.wikidata_quantities ─▶ stg_wikidata__quantities ────────────┼─▶ graph_facts ──▶ graph_facts.parquet
data/suppressions/*.csv ─────────────────────────▶ raw.suppressed_records ─────────────────────────────────────────┘  (and source_occurrences)
data/crosswalks/mrds_sources.csv ────────────────▶ raw.mrds_sources ─────────────────────────────┐
USGS MRDS ──▶ build/upstream/mrds_deposits/ ─────▶ raw.mrds_deposits ──▶ stg_mrds__deposits ─────┼─▶ source_occurrences ──────▶ source_occurrences.parquet
data/crosswalks/pleiades_sources.csv ────────────▶ raw.pleiades_sources ─────────────────────────┤
Pleiades ──▶ build/upstream/pleiades_places/ ────▶ raw.pleiades_places ──▶ stg_pleiades__workings ┤
             (Parquet + snapshot.json)            raw.upstream_snapshots ────────────────────────┘
OpenAlex, Crossref ──▶ build/upstream/reference_ ▶ raw.reference_candidates ▶ stg_references__candidates ─┬─▶ reference_checks ──▶ reference_checks.parquet
and each cited link    candidates/
(every reference in the documents and nodes) ────────────────────────────▶ stg_references__cited ──────┘
GitHub issues ──▶ build/upstream/github_reports/ ▶ raw.github_reports ────▶ stg_github__reports ─────────────────────┐
(label report)                                                                                                     │
                                                                                                                  ▼
                                                                              every mart above ─────────────▶ curation_queue ──▶ curation_queue.parquet

                                                                                                                                       manifest.json (last)
```

### 1b. Download (Dagster only)

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

The `upstream/wikidata_quantities` asset sends one SPARQL query to `https://query.wikidata.org/sparql` ([Wikidata and SPARQL](technologies/wikidata-and-sparql.md)). The query is built from the curated layer: the items in `data/crosswalks/wikidata_things.csv` and `ore_minerals.csv` (rows not rejected), and the property each quantity names in its `wikidata` field (today only `P1088`, Mohs hardness, expected in unit `Q199`). It asks for each item's best-ranked statements of those properties, with their amount, lower and upper bounds and unit, and keeps the CSV result unchanged as `wikidata_quantities.parquet`. Its `snapshot.json` adds the `query` itself, the number of `items` asked about and the `properties`. On 2026-11-24 it returned 18 statements for the 24 crosswalked items.

The `upstream/wikidata_items` asset sends a second query for the same items: each one's English label and description, and its chemical formula (P274), one row per formula. It names and describes the upstream ore minerals ([ADR 0045](../adr/0045-bring-ore-minerals-in-from-upstream-roast-sulphides-and-queue-the-gaps.md)). Its result, `wikidata_items.parquet`, has the columns `item`, `label`, `description` and `formula`.

The `upstream/pleiades_places` asset downloads `https://atlantides.org/downloads/pleiades/dumps/pleiades-places-latest.csv.gz`, the daily dump of every place in Pleiades (6.5 MB compressed; 42,544 places on 2026-11-24), checks its 26 columns and keeps it unchanged as `pleiades_places.parquet` ([ADR 0046](../adr/0046-place-ancient-mines-and-quarries-from-pleiades.md)). DuckDB reads the gzip directly, so the file hashed is the file converted. License: CC BY 3.0.

The `upstream/reference_candidates` asset looks up every work the curated layer cites ([ADR 0047](../adr/0047-check-citations-against-openalex-and-crossref.md), [OpenAlex and Crossref](technologies/openalex-and-crossref.md)). `cited_works` in `citations.py` reads every reference in the YAML and the ore crosswalk's (rows not rejected); a work is its citation text, so a book cited by eleven routes is looked up once. A work with a DOI is looked up by it in OpenAlex (`/works/doi:<doi>`, free) and Crossref (`/works/<doi>`). A work with a year in brackets is searched for: OpenAlex by its title (`search=`, what follows the year up to the first full stop, without an edition or "as summarized in"), Crossref by the whole citation (`query.bibliographic=`). Five candidates each are kept; a lookup that finds nothing is one row with no candidate. A web page or undated work isn't searched. Then every cited URL is requested once and its HTTP status kept. Requests pause between each other to stay inside Crossref's anonymous limit (one search a second) and OpenAlex's (ten a second); a 429, a server error, an answer cut short or one that isn't JSON is retried three times, then fails, and the download falls back to the cold backup. Only web (http and https) links are opened; any other address is recorded as `not a web address`, and a malformed one or one that can't be reached as `unreachable: <why>`, without stopping the rest. No key is needed; `OPENALEX_API_KEY`, if set, is sent. Only bibliographic fields are kept, never an abstract. The result, `reference_candidates.parquet`, has the columns `citation`, `service` (`openalex`, `crossref` or `link`), `lookup` (`doi`, `search` or `link`), `query`, `status`, `rank`, `record_id`, `doi`, `title`, `year`, `authors`, `type`, `oa_url`, `pdf_url` and `score` (Crossref's relevance). Its `snapshot.json` adds `crossref_url`, the number of `works` and how many were `searched`. On 2026-11-24: 43 works, 27 searched or looked up by DOI, 24 links; 242 rows, in about a minute and a half.

The `upstream/github_reports` asset reads the repository's open issues labelled `report` from GitHub's issues API (`GET /repos/nvelaborja/Capabilities/issues?labels=report&state=open`, 100 a page, up to 10 pages; unauthenticated, which allows 60 requests an hour), leaving out pull requests, which the API lists too ([ADR 0050](../adr/0050-report-withdraw-and-recheck-agent-facts.md)). Each is a report a reader opened from the app's "Report a problem" link, on the form `.github/ISSUE_TEMPLATE/report.yml`, whose answers GitHub writes into the issue's body under `### <label>` headings; `report_fields` reads them back. Only what the queue needs is kept: `number`, `url`, `title`, `created_at`, and the form's `fact`, `kind`, `reference` and `run`. Who reported it and what they wrote stay on GitHub. On 2026-11-26 there were none.

An OpenAlex API key raises its free daily allowance: put `OPENALEX_API_KEY=…` in `pipeline/.env`, which git ignores and the Dagster definitions read when they load (`definitions.py`; a variable already in the environment wins). Every OpenAlex request, the citation lookups and the agents' searches, sends it.

USGS refuses Python's default user agent, so downloads send a generic one (`dataset-snapshot/1.0`), and so do the Wikidata query and the reference lookups. None sends an email address, so Crossref treats us as an anonymous user.

**When a download fails.** If the network fails (offline, a refused connection, a timeout) and the dataset has a cold backup, the asset uses the backup instead: it logs a warning and records `copy: backup` and the `download_error` in its metadata, and the run goes on (`fetch_or_fall_back`). Any other failure, such as changed columns, fails the asset.

**Cold backups.** `snapshots/<dataset>/` in the repository holds a copy of each dataset, in git: the Parquet, every value unchanged but compressed with zstd (MRDS: 15 MB, down from 32 MB; Pleiades: 5.1 MB; the reference candidates: 28 KB), and the same `snapshot.json` as the download. `uv run capabilities backup` replaces a backup with a newer download (`back_up`); commit the result. Nothing in a build downloads: a build reads the downloads and the backups ([ADR 0044](../adr/0044-require-every-upstream-dataset-with-cold-backups-in-git.md)).

### 1a. Extract

`load_documents(root)` in the core library reads every YAML file under `data/` and `examples/`, in sorted path order, and works out each file's node type from its directory (`routes/` → `route`, `things/` → `thing`, and so on). A YAML syntax error, or a file outside a known directory, stops the build with the file's path. Schema validation is not part of the build: `capabilities validate` does that, and CI runs it before the build.

### 2. Load

`load_inputs` fills the DuckDB warehouse `build/warehouse.duckdb`. It takes the fingerprint of the inputs first (see [Freshness](#freshness)), then loads each kind of input, and records the fingerprint last:

- every curated document, whole, as JSON (overrides included);
- each crosswalk and the suppressions, as text;
- each upstream dataset's newest copy, as text: the latest download or the cold backup, whichever was retrieved later (`best_copy` in `upstream.py`). If a dataset has neither, the build stops here with `MissingSnapshot`, naming it and how to get one ([ADR 0044](../adr/0044-require-every-upstream-dataset-with-cold-backups-in-git.md)).

Every table is replaced on every build. The crosswalks and suppressions are loaded here rather than as dbt seeds, because dbt reads seeds only from inside its project ([ADR 0041](../adr/0041-place-sources-with-mrds-deposits-through-a-crosswalk.md)).

**`raw.curated_documents`**

| Column | Type | Meaning |
|---|---|---|
| `ordinal` | integer | Position in read order (sorted by path). Kept to the end so the app loads nodes in the same order as the YAML. |
| `node_type` | varchar | `quantity`, `thing`, `verb`, `route`, `profile`, `job` or `override`. |
| `id` | varchar | The document's `id`. |
| `document` | json | The whole document. |
| `path` | varchar | The file, relative to the repository root. |

**`raw.mrds_sources`**: the crosswalk `data/crosswalks/mrds_sources.csv`, every column text: `source_id`, `field` (`ore` or `commodity`), `value`, `deposit_type` (optional), `notes`. See [the data format](../data-format.md#crosswalk-datacrosswalkscsv).

**`raw.wikidata_things`**: the crosswalk `data/crosswalks/wikidata_things.csv`: `id`, `wikidata` (a Q id) and `notes`.

**`raw.ore_minerals`**: the crosswalk `data/crosswalks/ore_minerals.csv`: `id`, `wikidata`, `mrds_ore`, `class`, `mined_like`, `citation`, `url`, `supports`, `quote`, `status`, `proposed_by`, `notes` ([data format](../data-format.md)).

**`raw.wikidata_items`**: the Wikidata items snapshot, as text.

**`raw.suppressed_records`**: `data/suppressions/suppressed_records.csv`: `dataset` (`mrds`, `wikidata` or `pleiades`), `record_id` and `reason`.

**`raw.wikidata_quantities`**: the Wikidata snapshot as the query returned it, every column text: `item` (Q id), `property` (P id), `amount`, `lower`, `upper` (empty when the statement has no bounds) and `unit` (Q id; `Q199`, "1", for Mohs).

**`raw.mrds_deposits`**: the MRDS snapshot as downloaded, all 46 columns as text (`dep_id`, `site_name`, `latitude`, `longitude`, `country`, `state`, `commod1`–`commod3`, `dep_type`, `dev_stat`, `ore`, `yfp_ba`, `yr_fst_prd`, `score`, `url` and the rest).

**`raw.pleiades_sources`**: the rules `data/crosswalks/pleiades_sources.csv`: `target`, `places` (`mine` or `quarry`), `word`, `notes`.

**`raw.pleiades_places`**: the Pleiades snapshot as downloaded, all 26 columns as text (`id`, `title`, `description`, `featureTypes`, `tags`, `reprLat`, `reprLong`, `locationPrecision`, `minDate`, `maxDate`, `timePeriodsKeys` and the rest).

**`raw.reference_candidates`**: what OpenAlex and Crossref answered for each cited work, and how each cited link answered, every column as text (above).

**`raw.upstream_snapshots`**

| Column | Type | Meaning |
|---|---|---|
| `dataset` | varchar | The dataset: `mrds_deposits`, `wikidata_quantities`, `wikidata_items`, `pleiades_places` or `reference_candidates`. |
| `url`, `retrieved_at`, `sha256`, `license` | | From `snapshot.json`. |
| `row_count` | bigint | Rows in the snapshot. |
| `copy` | varchar | `download` or `backup`: which copy was loaded. |

**`raw.loads`**

| Column | Type | Meaning |
|---|---|---|
| `fingerprint` | varchar | The fingerprint of the inputs this load read. The manifest copies it, so an edit made while the build runs leaves the graph stale. |
| `loaded_at` | timestamptz | When the load ran. |

### 3a and 3b. Transform and test (dbt)

The build runs `dbt build` on `pipeline/dbt`: `capabilities build` through dbt's Python API, Dagster through dagster-dbt, which runs the dbt command line. `dbt build` runs each model and its tests in dependency order, and stops downstream models when a test fails.

**Source tests:**

- `raw.curated_documents`: `ordinal` and `path` are unique and not null; `node_type` is not null and one of the seven known types; `id` is not null.
- `raw.wikidata_things`: `id` is unique, not null and names a curated node; `wikidata` is unique and not null; `notes` is not null.
- `raw.wikidata_quantities`: `item`, `property` and `amount` are not null.
- `raw.ore_minerals`: `id` is unique; `wikidata` and `mrds_ore` are unique and not null; `class` is one of the ore classes or `none`; `citation` and `supports` are not null; `status`, when given, is `unverified`, `secondary` or `verified`.
- `raw.wikidata_items`: `item` is not null.
- `raw.suppressed_records`: `dataset` is `mrds`, `wikidata` or `pleiades`; `record_id` and `reason` are not null.
- `raw.pleiades_sources`: `target` is not null and names a curated node; `places` is `mine` or `quarry`; `word` and `notes` are not null.
- `raw.pleiades_places`: `id` is unique and not null.
- `raw.reference_candidates`: `service` is `openalex`, `crossref` or `link`; `lookup` is `doi`, `search` or `link`; `query` and `status` are not null.
- `raw.mrds_sources`: `source_id` is not null and names a curated node; `field` is `ore` or `commodity`; `value` and `notes` are not null.
- `raw.mrds_deposits`: `dep_id` is unique and not null.
- `raw.upstream_snapshots`: `dataset` is unique and not null; `retrieved_at` is not null.

**Singular tests** (`pipeline/dbt/tests/`):

- `crosswalk_maps_to_sources`: every crosswalk row names a source.
- `crosswalk_rows_are_distinct`: no rule is listed twice.
- `stg_mrds_coordinates_are_numbers`: no published coordinate fails to read as a number.
- `pleiades_rules_target_sources_or_classes`: every Pleiades rule's target is a source or a class.
- `occurrences_are_valid_points`: every occurrence is a valid point within latitude ±90 and longitude ±180.
- `ore_minerals_are_new_and_well_formed`: a row that builds nodes has an id that clashes with no curated node (nor its `-deposit` and `mine-` ids) and a `mined_like` that is a curated route whose label names the material it mines; a rejected row has neither.
- `crosswalked_items_are_in_the_wikidata_items_snapshot`: every item either crosswalk names (rejected rows aside) is in the items snapshot; one added since the last download stops the build until it is downloaded again.
- `wikidata_crosswalk_ids_are_items`: both crosswalks, rejected ore rows included, name Q ids.
- `wikidata_units_match`: every Wikidata value is in the unit its quantity expects (`wikidata.unit`); one in another unit would otherwise be read unconverted.
- `overrides_target_upstream_values`: every override's thing is in the Wikidata crosswalk, and its quantity is read from Wikidata. A value only the curated layer gives is corrected in its own file.

Macros in `pipeline/dbt/macros/citations.sql` reduce names and titles for comparing (`plain_text`: no accents, punctuation or capitals), split a title into its distinct words (`title_words`), and measure how alike two titles are (`word_overlap`: the words they share over the words either has).

Macros (`pipeline/dbt/macros/quantity_json.sql`) turn a low and high into a quantity value as the curated layer writes it (one number, or `[low, high]`; whole numbers as integers), and read the low and high ends back out of one.

**`stg_curated__documents`** (view, `models/staging/`). One row per document, with the fields every node has as columns.

| Column | From |
|---|---|
| `ordinal`, `node_type`, `id`, `document`, `path` | Unchanged from the raw table. |
| `kind` | `document ->> 'kind'` |
| `label` | `document ->> 'label'` |

Tests: `kind` not null; `label` not null for every node (overrides have none).

**`stg_curated__quantities`** (view). One row per thing and quantity it gives: `thing_id`, `quantity`, `value` (JSON, as written), `low`, `high`.

**`stg_curated__overrides`** (view). One row per override: `id`, `thing_id`, `quantity`, `value`, `replaces_dataset`, `replaces_value`, `replaces_low`, `replaces_high`, `reason`, `references`, `path`.

**`stg_curated__quantity_properties`** (view). Each quantity that names a Wikidata property: `quantity`, `property`, and the `unit` its values must be in.

**`stg_wikidata__quantities`** (view). One row per Wikidata statement, typed: `record_id` (the item), `property`, `amount`, `low` and `high` (the bounds, or the amount when there are none), `unit`.

**`stg_crosswalk__wikidata_items`** (view). Which Wikidata item each of our things is: the rows of both Wikidata crosswalks, rejected ore minerals left out. `graph_facts` reads values through it.

**`stg_wikidata__items`** (view). One row per item: `label`, `description`, and its first `formula`.

**`stg_ore_minerals__nodes`** (view). The upstream nodes ([ADR 0045](../adr/0045-bring-ore-minerals-in-from-upstream-roast-sulphides-and-queue-the-gaps.md)): for each ore crosswalk row, three documents, with `node_type`, `id`, `kind`, `label`, `document`, `provenance` and `position` (their order after the curated nodes):

- the mineral: a material in its class, `origin: extracted`, labelled from Wikidata (capitalised; MRDS's name if Wikidata has none), described from Wikidata's description and formula and the row's `notes`, citing the row's reference;
- `<id>-deposit`: a regional source;
- `mine-<id>`: the `mined_like` route as a JSON patch, with the mineral, its deposit, its label (the template's, with the template material's name replaced) and its outputs swapped in. Its references are the template's, each made `unverified`, with `supports` prefixed "Cited for the route this copies (<template label>): ".

Each node's provenance is `{"layer": "upstream", "crosswalk": "data/crosswalks/ore_minerals.csv", ...}` with what it came from: the mineral `"dataset": "wikidata", "record": <Q id>, "url": ...`; the deposit `"dataset": "mrds", "record": "deposits listing <MRDS name> as an ore mineral"`; the route `"copied_from": <template>`. A row an agent proposed adds `"proposed_by": <run>` to all three, and its `quote` joins the mineral's reference ([ADR 0048](../adr/0048-run-agents-through-claude-code-on-a-claude-subscription.md)); empty values leave the keys out.

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

**`stg_pleiades__workings`** (view). One row per Pleiades place typed as a mine (`mine-2`), a quarry (`quarry`) or the deprecated "mine, quarry" (`mine`); 830 on 2026-11-24.

| Column | From |
|---|---|
| `record_id`, `name`, `description`, `url` | `id`, `title` (null when "Untitled"), `description`, and `https://pleiades.stoa.org/places/<id>` |
| `kinds` | `mine` and/or `quarry`: the deprecated type is both |
| `materials` | `tags`, lower case, without DARE's bookkeeping (`dare:…`) and tags that repeat the type |
| `text` | Title and description, lower case, with "Iron Age" removed, for matching a whole word |
| `latitude`, `longitude` | `reprLat`, `reprLong`, as numbers |
| `location_precision` | `locationPrecision`: `precise`, `rough`, `related` or `unlocated` |
| `attested_from`, `attested_to` | `minDate`, `maxDate`, as integers (negative is BC) |
| `periods` | `timePeriodsKeys`, split into a list |

**`graph_facts`** (mart, written as Parquet). Where each quantity value comes from ([ADR 0043](../adr/0043-take-quantities-from-wikidata-with-upstream-first-and-overrides.md)): one row per thing and quantity that has a value from any layer.

| Column | Meaning |
|---|---|
| `id` | `<thing>/quantities.<quantity>`, e.g. `granite/quantities.hardness_mohs`. |
| `node_id`, `field` | The thing, and `quantities.<quantity>`. |
| `layer` | Where `value` comes from: `override`, else `upstream`, else `curated`. |
| `value` | The value the graph uses (JSON: a number or `[low, high]`). |
| `curated_value`, `upstream_value` | Each layer's value, or null. Several best-ranked Wikidata statements become one range. |
| `disagrees` | Both layers have a value and they differ. |
| `upstream` | `{"dataset": "wikidata", "record": "Q41177", "url": ..., "retrieved_at": ...}`, or null. |
| `override` | `{"id", "path", "reason", "references", "replaces", "stale"}`, or null. `stale` is true when upstream no longer has the value the override says it replaces. |

Suppressed Wikidata items are left out before the choice is made. Tests: `id` unique and not null; `node_id` not null and in `graph_nodes`; `layer` one of the three; `value` not null.

With the 2026-11-24 snapshots there are 30 facts: 18 from Wikidata and 12 curated. The curated layer has no value where Wikidata gives one ([ADR 0044](../adr/0044-require-every-upstream-dataset-with-cold-backups-in-git.md)), so none disagree.

**`graph_nodes`** (mart, `models/marts/`, written as Parquet). The built graph: the curated nodes in read order, then the upstream nodes of `stg_ore_minerals__nodes`.

| Column | Meaning |
|---|---|
| `ordinal` | Read order. |
| `node_type`, `id`, `kind`, `label` | As above. Overrides aren't nodes and are left out. |
| `document` | The full document as JSON: what the app parses. Its `quantities` are the values `graph_facts` chose, so the reasoner uses upstream values and overrides without knowing where they came from. |
| `provenance` | Where the node came from: `{"layer": "curated", "path": "<file>"}`, or an upstream node's (above). Where each of its quantity values came from is in `graph_facts`. |

Tests: `ordinal` unique and not null; `id` unique and not null, across every type of node; `provenance` not null.

**`source_occurrences`** (mart, written as GeoParquet). Where each source kind is found ([ADR 0036](../adr/0036-place-sources-and-profiles-in-space-and-time.md)). It has one row per source kind and record, for every MRDS deposit or Pleiades mine or quarry with coordinates that matches a rule and isn't suppressed. MRDS's rules are those of `mrds_sources`, plus one per upstream ore mineral: its deposit is every MRDS deposit listing it as an ore. Pleiades' are those of `pleiades_sources`: a place matches when it is of the rule's kind and names its word as a tag or whole in its title or description. A Pleiades copper, iron or tin mine is an occurrence of the ore class (copper ore and copper sulphide ore, iron ore, tin ore), since it doesn't say which ore ([ADR 0046](../adr/0046-place-ancient-mines-and-quarries-from-pleiades.md)). A record that matches two source kinds appears twice.

| Column | Meaning |
|---|---|
| `id` | `<source_id>/<dataset>/<record_id>`, e.g. `hematite-deposit/mrds/10008106`, `copper-ore/pleiades/707452`. |
| `source_id` | The source kind, or the ore class for a Pleiades mine. |
| `dataset`, `record_id` | `mrds` and the MRDS `dep_id`, or `pleiades` and the place's id. |
| `name`, `country`, `admin_area`, `development_status`, `deposit_type`, `ore_minerals`, `commodities`, `record_quality`, `url` | From staging. |
| `geometry` | A point, `ST_Point(longitude, latitude)`, in WGS 84 longitude and latitude (`OGC:CRS84`). |
| `longitude`, `latitude` | The same point as numbers, for readers without a spatial library. |
| `first_production_year`, `first_production_qualifier` | As MRDS gives them. |
| `worked_by_year` | The year by which it is known to have been worked: the first production year, unless production began only "after" it. |
| `state` | MRDS: `worked` if `worked_by_year` is known, otherwise `present` ("present, not known to be worked by then"). Pleiades: always `worked`, with `worked_by_year` empty (it needs each period's end year; M4). |
| `attested_from`, `attested_to`, `periods` | Pleiades: the years it is attested from and to, and its periods. Null for MRDS. |
| `approximate` | Pleiades: true unless its location is precise. Null for MRDS, which doesn't say. |
| `matched_on` | The rule that matched, e.g. `ore: Hematite`, `tag: copper` or `text: copper`. |
| `provenance` | `{"layer": "upstream", "dataset": "mrds" or "pleiades", "record": ..., "url": ..., "retrieved_at": ...}`. |

Tests: `id` is unique and not null; `source_id` is not null and names a node in `graph_nodes`; `dataset` is `mrds` or `pleiades`; `geometry`, `state` and `provenance` are not null; `state` is `worked` or `present`. Also the valid-points test above.

From the snapshot of 2026-11-22 there are 14,488 occurrences of 8 source kinds: 4,960 for malachite, 4,216 for limestone, 2,655 for hematite, 1,162 for granite, 1,083 for native copper, 238 for diamond gravel, 171 for tin gravel and 3 for flint. Of these, 1,968 have a working year; the earliest is 1505. With Pleiades' snapshot of 2026-11-24, 290 ancient mines and quarries add 421 more: 118 each for copper ore and copper sulphide ore, 94 limestone, 68 iron ore, 14 granite, 8 tin ore and 1 flint. 35,732 in all, with the ore minerals' deposits.

The marts' `external` materialization (a dbt-duckdb feature) writes each result to `build/graph/<model>.parquet` instead of keeping it as a table in the warehouse. Two quirks matter to readers of a mart that comes out empty (for example `source_occurrences.parquet` from a dataset with no matching records):

- dbt-duckdb writes an empty table as **one row of nulls**, so its columns keep their types. Skip rows whose `id` is null; the manifest's counts already do.
- DuckDB writes no GeoParquet metadata for a file with no rows, so `geometry` reads back as WKB bytes. Cast it (`geometry::geometry`) before using spatial functions.

**`curation_queue`** (mart, written as Parquet). The gaps the build found, as a to-do list ([ADR 0045](../adr/0045-bring-ore-minerals-in-from-upstream-roast-sulphides-and-queue-the-gaps.md)). One row per item:

| Column | Meaning |
|---|---|
| `id` | `<kind>/<subject>`. |
| `kind` | `reported`, `ore_candidate`, `extracted_without_route`, `source_without_places`, `route_unverified`, `upstream_disagreement`, `stale_override`, `unread_reference` or `unmatched_place`. |
| `subject`, `label` | What the item is about: an MRDS ore name (lower case), a node or fact id, or a work's check id (`ref-…`, labelled with its citation), and how to show it. |
| `detail` | What is missing, and what to do. |
| `priority` | For reports, the number of open issues about the fact; for ore candidates, the number of MRDS deposits of copper, iron or tin listing the mineral as an ore; for unread references, the number of routes citing the work; for unmatched places, the number of places; otherwise null. |
| `evidence` | JSON: the deposits and metals for a candidate, the values behind a disagreement, and so on. |

A report is every open issue about one fact (by the fact the app's link named; an issue naming none is an item of its own, `#<number>`), labelled with the node's label, listing each issue, with the runs and references they name in `evidence`. Reports come first, before every other kind: someone told us the graph is wrong ([ADR 0050](../adr/0050-report-withdraw-and-recheck-agent-facts.md)). An ore candidate is a mineral listed on at least 20 such deposits and not yet reviewed: in neither the ore crosswalk nor `mrds_sources`. An unmatched place group is the located Pleiades mines and quarries that no rule matches and none suppressed, by a material they name (gold, marble…), or naming none. They come last, after every other kind: where a material was found matters least to the app's questions ([ADR 0046](../adr/0046-place-ancient-mines-and-quarries-from-pleiades.md)). An unread reference is a work not yet verified everywhere it is cited: the reading queue, ranked by how many routes cite it, saying what the check found and offering a free copy ([ADR 0047](../adr/0047-check-citations-against-openalex-and-crossref.md)). Tests: `id` unique and not null; `kind` one of the nine; `detail` not null. With the 2026-11-24 snapshots there are 264 items: 135 ore candidates (galena first, on 6,326 deposits), 49 routes with only unverified references, 2 sources with no places, 43 unread references (Craddock and Tylecote first, 11 routes each), and 35 groups of unmatched places (236 naming no material, then gold, 100). `uv run capabilities queue` prints them.

**`stg_references__cited`** (view). Every reference in the graph, one row per use: `node_id`, `node_type`, `citation`, `doi` and `url` (with whitespace trimmed from both ends, as the download trims it), `status`, and `copied`: true for a mining route copied for an ore mineral, whose references are its template's, marked unverified (ADR 0045). It walks each document with `json_tree`, so a reference nested anywhere (a route's, a profile item's, an override's) is found: in the curated documents, example jobs included, and in the upstream nodes (an ore mineral's reference, and those a copied mining route keeps).

**`stg_references__candidates`** (view). The candidates of `raw.reference_candidates`, typed (`rank`, `year` integers; `score` a double; `doi` lower case), with `title_words`, `main_title_words` (before a colon) and `plain_authors` for comparing. Link rows are left out.

**`reference_checks`** (mart, written as Parquet). Every cited work, checked ([ADR 0047](../adr/0047-check-citations-against-openalex-and-crossref.md)). From the citation it reads the year in brackets, the title after it (up to the first full stop, without an edition), and the first author's surname at the start. A candidate's title score is the `word_overlap` of the two titles, whole or before a colon, whichever is higher. A candidate is the work when its title scores at least 0.8, it isn't a review, its authors include the surname, and its year is the cited year give or take one (another edition is only possible). The surname must be a whole word among the authors (Fall isn't Fallon). A review (`book-review`, `review`) with the title, from the cited year to five years after, is a review of it. A title scoring at least 0.5 is a possible match. The best candidate is the work, else a review, else a possible match, by title score, closeness of year, OpenAlex first, then rank.

| Column | Meaning |
|---|---|
| `id` | `ref-` and the first 12 hex digits of the citation's MD5. |
| `citation`, `doi` | The work, and the DOI cited for it (the largest, if uses disagree; `citations.py` makes the same choice). |
| `statuses`, `verified` | The statuses its uses give, and `verified` when every use is, leaving out copied routes: they follow their template, where a person reads the work. A work cited in the ore crosswalk takes the row's `status`. |
| `cited_by`, `routes` | The nodes citing it, and how many are routes (copied mining routes included). |
| `result` | `found`, `review_found`, `possible`, `not_found`, `doi_disagrees` (the DOI cited leads to a different work), `not_searched` (a web page or undated work) or `not_checked_yet` (not looked up the way it is cited now: cited since the last download, or its DOI added or changed since). |
| `note` | Why, in words: what differs for a possible match ("the year differs (cited 1992, found 1978): perhaps another edition"), and the meaning of the other results. |
| `match_service`, `match_id`, `match_doi`, `match_title`, `match_year`, `match_authors`, `match_type`, `title_score` | The record matched, for a work found, a review, a possible match or a wrong DOI's work. |
| `free_copy` | For a work found only: OpenAlex's PDF link, else its best open-access link, for the record matched or another OpenAlex record with its DOI. Not for a review or a possible match, whose copy may not be the work. |
| `links` | JSON: each URL cited for the work, its `status` and `state`: `works` (2xx or 3xx), `refused` (401, 403 or 429: the site turns automated requests away) or `broken` (any other answer, `unreachable`, or `not a web address`). |
| `checked_at` | When the candidates were retrieved. |

Tests: `id` and `citation` unique and not null; `result` one of the seven; `cited_by` not null. A check never changes a reference's status. With the lookup of 2026-11-24: 16 works found, 4 known only by reviews, 5 possible, 2 not found and 16 not searched; 23 of 24 links work and Britannica's refuses; 4 works have a free copy.

### 4. Publish

The build counts the rows in each Parquet file and writes **`build/graph/manifest.json`**, with the fingerprint recorded at load time:

| Field | Meaning |
|---|---|
| `format_version` | The artifact's shape (`FORMAT_VERSION` in `built.py`, now 5: `reference_checks.parquet` was added). Bumping it makes every older build stale. |
| `fingerprint` | SHA-256 over the path and bytes of every input file and of the pipeline's code (below). |
| `built_at` | UTC time of the build. |
| `git_commit` | The commit checked out, if git is available. |
| `tables` | Row count per file, e.g. `{"graph_nodes.parquet": 197, "graph_facts.parquet": 30, "source_occurrences.parquet": 35732, "curation_queue.parquet": 264, "reference_checks.parquet": 43}`. |
| `upstream` | The snapshot loaded for every dataset: `url`, `retrieved_at`, `sha256`, `rows`, `license`, and `copy` (`download` or `backup`). |

The manifest is written **last**. If anything fails earlier, no manifest matches the current inputs, so the failed build is never read as current.

## Orchestration (Dagster)

The same steps are Dagster assets ([Dagster](technologies/dagster.md)). `assets.py` defines them, and `definitions.py` is the module Dagster loads, building into the same build directory as `capabilities build`.

| Asset | Group | Step | Checks |
|---|---|---|---|
| `upstream/mrds_deposits`, `upstream/wikidata_quantities`, `upstream/wikidata_items`, `upstream/pleiades_places`, `upstream/reference_candidates`, `upstream/github_reports` | upstream | Download (`fetch_or_fall_back` in `upstream.py`), or the cold backup when the network fails. Their URLs come from the `downloads` resource (`openalex_url` and `crossref_url` for the references), which tests point at a local zip or gzip, local stand-ins for the SPARQL endpoint, for OpenAlex and Crossref and for GitHub's issues, or a port that refuses connections. | None |
| `raw/curated_documents`, `raw/mrds_sources`, `raw/wikidata_things`, `raw/ore_minerals`, `raw/suppressed_records`, `raw/pleiades_sources`, `raw/mrds_deposits`, `raw/wikidata_quantities`, `raw/wikidata_items`, `raw/pleiades_places`, `raw/reference_candidates`, `raw/github_reports`, `raw/upstream_snapshots` | raw | Load (`load_inputs`): one multi-asset, since the fingerprint is taken once before anything is read. The keys are the dbt sources' keys, so lineage runs into dbt. | The source tests above |
| `stg_curated__documents`, `stg_curated__quantities`, `stg_curated__overrides`, `stg_curated__quantity_properties`, `stg_crosswalk__wikidata_items`, `stg_wikidata__items`, `stg_ore_minerals__nodes`, `stg_mrds__deposits`, `stg_wikidata__quantities`, `stg_pleiades__workings`, `stg_references__cited`, `stg_references__candidates`, `stg_github__reports` | staging | dbt views | Their tests above |
| `graph_facts`, `graph_nodes`, `source_occurrences`, `reference_checks`, `curation_queue` | marts | dbt marts, written as Parquet | Their tests above |
| `graph_manifest` | marts | Publish (`write_manifest`) | None |

**The agent job.** `agent_curation` is a job, not an asset, so "Materialize all" never starts it. Its one op, `curate`, takes its task, size and settings as run config (`task`, `items`, `names`, `evaluate`, `find_only`, the two models and their efforts, the usage thresholds, `pull_request`, `base`) and the `downloads` resource for the gate's downloads. See [Agent curation](#agent-curation). `agent_recheck`, also a job and only started by hand, checks merged agent facts again; see [Withdrawing and re-checking](#withdrawing-and-re-checking).

Every dbt test that belongs to one model or source is an asset check (94 today). Tests that compare two tables, such as `crosswalk_maps_to_sources`, still run in `dbt build` but aren't attached to an asset. "Materialize all" downloads every dataset again, and looks up every cited work; to rebuild from the snapshots you have, select everything except the `upstream` group. Loading the definitions runs `dbt parse` first, so the asset list always matches the dbt project. dbt's files for each Dagster run go in `build/dbt/target/<run>/`.

## Agent curation

Agents work through the curation queue, one task a run: ore candidates, for which they propose rows of the ore crosswalk, or routes whose references are all unverified, for which they propose a quoted source ([ADR 0035](../adr/0035-propose-curated-facts-with-audited-agents.md), [ADR 0048](../adr/0048-run-agents-through-claude-code-on-a-claude-subscription.md), [ADR 0049](../adr/0049-have-agents-quote-sources-for-unverified-routes.md), [Claude Code agents](technologies/claude-code-agents.md)). The run, the curator, the usage thresholds, the library of sources, the audit log, the gate and the pull request are the same for both; a task (`agents/task.py`) supplies its items, what a passage must say, its prompts, proposal, checks and the files it changes. The diagram and table below follow ore candidates; [Route sources](#route-sources) says what differs. It is a stage beside the build, not in it: started by hand, it reads the built graph's queue and ends in a draft pull request against the curated layer, which a person merges or closes. Nothing an agent proposes reaches the built graph until then.

```
curation_queue.parquet ──▶ ore candidates, top N ──▶ for each, one at a time:
                                                     find, in code: Wikidata item (search, mineral species),
                                                     sources (pages the repository cites, OpenAlex open-access works),
                                                     passages (sentences naming the mineral and ore or smelting)
                                                       ▼ (no item or no passages: skipped, no model asked)
                                                     proposer (claude -p: no tools) chooses a class and a passage
                                                     ──▶ code makes the row: quote, citation and URL from the passage
                                                       ▼
                                                     mechanical checks: class and template, Wikidata item, id, site,
                                                     page downloaded by us (HTML, PDF, text), quote on it word for word
                                                       ▼ (fail: back to the proposer, with the reasons; two proposals at most)
                                                     reviewer (claude -p: no tools) reads the downloaded page ──▶ accept / revise / reject
accepted rows ──▶ temporary worktree, branch agents/<run>, from origin/main:
                  write the crosswalk ─▶ download Wikidata items and quantities, OpenAlex and Crossref ─▶ build and test
                  ─▶ drop a row whose cited DOI leads to another work, and check the rest again
                  ─▶ back up the three snapshots, regenerate CREDITS.md, write data/agent_runs/<run>.json
                  ─▶ commit, push, gh pr create --draft
every call, check and outcome ──▶ audit/agents.duckdb (append-only), and the run's summary to audit/runs/<run>.json
```

| Step | Code | What it checks or writes |
|---|---|---|
| Preflight | `claude.check_login`, `branch.check_gh` | `claude auth status` says `claude.ai` and no API key is set; `gh` is logged in. Before anything is spent. |
| Items | `ore_candidates.queue_candidates`, `evaluation_set` | The first N `ore_candidate` items of the current build's queue, most widely listed first. An evaluation takes the minerals a person decided instead, treating their rows as undecided. |
| Find | `sources.Library`, `sources.known_sources`, `web.py` | The Wikidata item: `wbsearchentities` for the name, keeping the item called exactly that that is an instance of *mineral species* (Q12089225) or a subclass of a class of minerals (a parent whose English label says "mineral"); a one-word name is tried again as "native <name>"; an item the ore crosswalk has is skipped as decided, and a curated thing's item is left to a person. Every search hit is recorded with why it was or wasn't taken; only the classes the decision needs are looked up. The sources: pages the repository cites (crosswalk rows and the curated layer's references; an evaluation leaves out pages only the evaluated rows cite), then OpenAlex's open-access works for "<mineral> archaeometallurgy" and "<mineral> ancient smelting" (five each), each downloaded once a run. The passages: sentences of 40 to 1,000 characters naming the mineral and ore, smelting, roasting or a metal, with the sentence either side, never a caption; three a source, twelve in all, ranked across sources. No item or no passages: the item is `skipped`, and no model is asked. |
| Choose | `curate.Curator`, `prompts/ore_proposer.md` | Sonnet 5.5 at medium effort by default (`proposer_model`, `proposer_effort`), no tools, 3 turns, answering to `proposal_schema`: decision, class or `none`, the passage's number, supports, notes; or `unsure`. Code makes the proposal: the quote is the chosen sentence, the citation and URL its source's (the repository's own citation, or one made from OpenAlex's record). |
| Check | `ore_candidates.check`, `web.py` | The class has a route to be mined like (the one its rows use); the Wikidata item exists, wasn't merged, is called the mineral's name, and is in no crosswalk; the id is new; the site may be cited (not Mindat); the page is on the public web (never this machine or its network, nor a redirect there) and loads; the quote (40 to 1,000 characters) is on it word for word, ignoring case and typography, and names the mineral. |
| Challenge | `prompts/ore_reviewer.md` | Sonnet 5.5 at high effort by default (`reviewer_model`, `reviewer_effort`) with no tools, 3 turns: the proposal, the Wikidata item and 2,500 characters each side of the quote, as downloaded. `task.review_schema`: accept, revise or reject, with objections. Reviewing a revision, it is shown the changes it asked for, and judges whether they were made before raising anything new. |
| Gate | `branch.gate`, `branch.work_check` | Validates the worktree's data (`capabilities validate`), downloads `wikidata_items`, `wikidata_quantities` and `reference_candidates` for it, and builds it. The citation check's result is noted on each row; only `doi_disagrees` (the DOI cited leads to another work) drops one, since the row's own page was downloaded and its quote found. A rejected mineral's (`none`) isn't looked up. |
| Publish | `branch.publish` | The crosswalk, the three refreshed backups, `CREDITS.md` and `data/agent_runs/<run>.json`, in one commit on `agents/<run>` (`feat(data): agent proposals for …`); a draft pull request titled "Agent proposals: …". Text from pages and agents in its body can't mention anyone on GitHub. |

If OpenAlex refuses a search (429: its free daily allowance is spent), the run stops there, as it does at the plan's limit, rather than skip items as if nothing spoke of them; `OPENALEX_API_KEY` raises the allowance. Other failed searches are listed in the summary (`sources.openalex_failures`), with how every page download answered (`sources.page_statuses`).

`names: ["Gold", "Silver"]` runs the items named (minerals by MRDS name, routes by id), in that order, instead of the top of the queue (a mineral the queue doesn't list is run all the same, a route only if it is a curated one; an evaluation lists in its summary, as `not_evaluated`, any it has no answer for); tests name theirs, so they don't depend on what the queue holds.

`find_only: true` runs the *Find* step alone and records what each item would be offered, asking no model: it uses none of the plan, only OpenAlex searches and downloads.

A run stops before its next item when the plan's five-hour usage, as Claude Code last reported it, reaches `stop_at_five_hour` (0.8) or the weekly reaches `stop_at_seven_day` (0.9), and at once if a call says the limit is reached. A call that fails still reports what it used, and that counts. The thresholds are shares (0.8, not 80): a run refuses anything outside 0 to 1, which would never stop it. What was accepted before it stopped still goes through the gate.

### Route sources

`task: route_sources` ([ADR 0049](../adr/0049-have-agents-quote-sources-for-unverified-routes.md), `agents/route_sources.py`) works through the queue's `route_unverified` items that are curated routes; the mining routes copied for each ore mineral follow their template, and the pull request names a template's copies. Where it differs from ore candidates:

| Step | What it does |
|---|---|
| Find | No Wikidata item. The sources: the route's own references' pages first (a reference's URL, or the free copy OpenAlex lists for a work the citation check `found`, read from `reference_checks.parquet`), then the pages the repository cites, then OpenAlex's open-access works for "<label> archaeology" and "<label> experimental archaeology". A passage names what the route makes (its thing; for a route that does something, its tools and technique) and something else of it (its materials, tools or technique, or what it does, from its label's first word unless that is as broad as "making", in a verb's own forms: "alloying" finds "alloyed", never "allow"). A sentence starting with a number, or carrying a journal's volume and issue (a PDF's running header), is never offered, for either task. |
| Choose | `prompts/route_proposer.md`: the route as a person reads it (what it makes, what it takes and under what conditions, its notes, its references and what each supports), and the passages, those from its own references marked. It answers with a passage's number and what it supports, or `unsure`. A passage from one of its own references becomes a quote for that reference (with the page's URL if it had none), keeping what it says it supports; any other becomes a new reference, its citation the repository's or OpenAlex's. |
| Check | A new reference cites a work the route doesn't (citation or URL) and says what it supports; an existing one has no quote yet and is `unverified` (a route named for a run needn't be in the queue, and a person's verified or secondary reference never takes an agent's quote); then the site, page and quote checks of ore candidates, and that the quote names what the route makes or uses. |
| Challenge | `prompts/route_reviewer.md`: the route, its references, the proposal and the page around the quote. |
| Gate and publish | `RouteSources.write` edits the route's file as text (`agents/yaml_edit.py`): the reference's lines are inserted, or the fields into one (found by its citation, as the base branch may order the references differently than the run's copy), and the file is parsed again; an edit that changes anything else, or a file whose references aren't a block list, is refused. A change that can't be written rejects only its item: the gate checks the rest. Every reference stays `unverified`, with `proposed_by`. The commit holds the route files, not the crosswalk. |

There is no evaluation set: `evaluate: true` refuses the task. Once merged, the queue's item for a route with a quote says "A quote is ready to check".

**The audit log** (`audit/agents.duckdb`, not in git; `agents/audit.py`). Rows are only ever added:

| Table | One row per |
|---|---|
| `run_starts` | Run started: its id, task (`recheck` for a re-check), mode (`propose`, `evaluate`, or a re-check's `checks` or `checks and review`), settings with the prompts' versions, login method and plan, and git commit |
| `calls` | Call to an agent: item, attempt, role, prompt version, model (the alias asked for and the model it ran on) and settings, the prompt, the answer, every tool call (searches and URLs), token usage, API-equivalent cost, the plan's usage after it, turns, time, error, and every event printed |
| `checks` | Mechanical check: its name, whether it passed, and why |
| `outcomes` | Item's outcome (`accepted`, `rejected`, `sent_back`, `unsure`, `failed`; for a re-check, each fact's `holds`, `fails`, `objected` or `failed`) and reason, with the row when accepted. A later row for the same item (dropped at the gate) supersedes an earlier one |
| `run_ends` | Run finished, however it ended (an error too): why it stopped early, if it did, the outcomes, the pull request, and the usage |

```python
import duckdb
duckdb.sql("select run_id, item, outcome, reason from 'audit/agents.duckdb'.outcomes order by recorded_at").show()
duckdb.sql("select run_id, role, count(*), sum(cost_usd) from 'audit/agents.duckdb'.calls group by all").show()
```

## Withdrawing and re-checking

Agents' facts that turn out wrong are found by readers' reports and by re-checks, and taken out by withdrawals ([ADR 0050](../adr/0050-report-withdraw-and-recheck-agent-facts.md)).

```
app: "Report a problem" ──▶ GitHub issue (label report) ──▶ upstream/github_reports ──▶ curation_queue: reported (first)
admin: agent_recheck ──▶ code's checks (free), reviewer if asked (plan) ──▶ summary, audit log; report_failures ──▶ issue
person: capabilities withdraw ──▶ fact removed, data/withdrawals.csv ──▶ pull request "Closes #<issue>"
```

| Step | Code | What it does |
|---|---|---|
| Report | `web/src/detail/report.ts`, `ReportLink.tsx`; `.github/ISSUE_TEMPLATE/report.yml` | On every node, line, route and reference in the detail pane: a link to a new issue on the report form, the fact's id, kind, a reference's citation and the agent run filled in from the link's query. The app sends nothing. |
| Queue | `upstream/github_reports`, `stg_github__reports`, `curation_queue` | Open reports, one item per fact (above). |
| Withdraw | `packages/core/src/capabilities/withdraw.py`, `capabilities withdraw` | Removes an agent's ore row (CSV rewritten, every other row byte for byte), an agent's reference, or an agent's quote on a person's reference, with the URL it brought (what the run changed is read from its summary in `data/agent_runs/`); the route file is edited as text and parsed again (`capabilities/yaml_edit.py`). Appends to `data/withdrawals.csv`. Refuses a person's fact, a route's only reference (every route cites one), and an edit it can't make as text (edit the file by hand). A copied mining route (`mine-<mineral>`) has no file: its fact is taken off the route it was copied from (`mined_like`), and so off every copy. `validate` then refuses the quote back on the same subject, and agents' checks include `quote_not_withdrawn`. |
| Re-check | `agents/recheck.py`, the `agent_recheck` job | Chooses merged agent facts by `runs`, `prompt_versions` or `models` (matched in the run summaries), or `every_fact`; one is required. Each task rebuilds its facts as the proposals they were, on their items as they were before (`Task.merged`, `Task.before_merging`): an ore row with the agents' rows left out of the context, a route without the agent's reference or with the person's reference unquoted and `unverified`, as it was when quoted (a person may have verified it since). Code's checks run again; with `reviewer: true`, the reviewer is asked about each fact that passes, on the plan, stopping at the usual thresholds. Outcomes: `holds`, `fails`, `objected`; and, listed as `not_rechecked` in the summary, `unreachable` (a check failed only because Wikidata or the cited site didn't answer: a connection error, 429 or 5xx) and `failed` (the reviewer couldn't be asked). Changes no data. The summary is `audit/rechecks/<id>.json`, written even if the re-check breaks, and the audit log records it as a run (each fact's checks, review and outcome under its item's name) (`task` `recheck`, mode `checks` or `checks and review`). With `report_failures: true`, each fact that `fails` or is `objected` to becomes a `report` issue in the form's shape, unless an open report already names it: the same fact in its Fact field, and for a reference the same citation, whether a reader's or an earlier re-check's. |

## Freshness

A build is current when `manifest.json` exists, its `fingerprint` equals the fingerprint of the inputs now, and `graph_nodes.parquet` exists. The fingerprint covers:

- `data/**/*.yaml`, `data/**/*.csv` (crosswalks and suppressions), `examples/**/*.yaml` and `schema/*.json` under the repository root;
- each upstream snapshot's `snapshot.json`, downloaded in the build directory and backed up in `snapshots/`, so downloading again or refreshing a backup makes the graph stale;
- the pipeline's code, wherever the pipeline package is installed: `src/capabilities_pipeline/*.py`, `dbt/**/*.sql`, `dbt/**/*.yml`;
- the artifact's `format_version`.

`current_graph()` (used by `need`, `explore`, `check` and the server) rebuilds when the build isn't current, printing a note to stderr, and then loads it. The server loads the graph once at start-up, so restart it after changing data.

## Who reads what

| Reader | Reads | Why |
|---|---|---|
| `need`, `explore`, `check`, `serve` | The built graph (`load_built` via `current_graph`), and `graph_facts.parquet` (`load_facts`) as `Graph.facts` | They answer questions from what the pipeline built, upstream values included. The detail pane shows where each quantity value came from (`quantity_source` in `views.py`). |
| `serve`, for the map | `source_occurrences.parquet` (`load_occurrences`) and the manifest's `upstream` | Where each source is found, for `GET /api/occurrences/{id}` ([ADR 0042](../adr/0042-show-where-things-are-found-on-a-maplibre-map.md)). It reads the longitude and latitude columns, so the server needs no spatial extension. |
| `validate` | The curated YAML (`Graph.from_curated`) | It checks what people wrote, file by file. |
| `credits` | The curated YAML, and the references of `data/crosswalks/ore_minerals.csv` | The works cited are in the curated layer. |
| `queue` | `curation_queue.parquet` (`load_queue`) | The gaps the last build found, the reading queue among them. |
| `serve`, for the detail pane | `reference_checks.parquet` (`load_reference_checks`) as `Graph.reference_checks` | What the check found for each reference's work, shown under it (`reference_check` in `views.py`). |
| Reasoner and view tests | The built graph (the `graph` fixture: built once per test run from the cold backups), the curated YAML (`curated_graph`), or small graphs built in the test | The answers the app gives. |
| Pipeline and server tests, `test_cli` | A build made once per test run in a temporary directory, from the cold backups | They test the real path, with no network. |
| Upstream tests (`pipeline/tests/test_upstream.py`) | A snapshot of 14 real MRDS records (`pipeline/tests/fixtures/mrds-sample.csv`), "downloaded" from a local file | Every crosswalk rule and year rule, with no network. |
| Pleiades tests (`pipeline/tests/test_pleiades.py`) | 13 real Pleiades places (`pipeline/tests/fixtures/pleiades-sample.csv`), gzipped and "downloaded" from a local file; and every place, from the cold backup | Matching by tag and by text, "Iron Age", class-level copper mines, dates, approximate locations, unmatched places in the queue, suppressions, and class-level places on a mineral's map. |
| Citation tests (`pipeline/tests/test_citations.py`) | What OpenAlex and Crossref answered on 2026-11-24 (the committed backup, `snapshots/reference_candidates/`), served by a local stand-in for both (`scholarly_endpoint` in `conftest.py`), with links answered from the backup too (`lookups_offline`); a local service that is always busy or answers a web page | A download gives back the backup unchanged; each work looked up once; DOIs, searches and web pages; retries and the fallback; only web links opened; every result, a wrong DOI, a citation or DOI added since the lookup, free copies only for works found, and the reading queue (copied routes and the ore crosswalk's `status`), with no network. |
| Ore mineral tests (`pipeline/tests/test_ore_minerals.py`) | The built graph from the cold backups | The upstream nodes, roasting, and the queue. |
| Agent tests (`pipeline/tests/test_agents.py`) | A stand-in for `claude` that plays back scripted answers as stream-json (`fixtures/agents/fake_claude.py`), a fake web of made-up pages and Wikidata items, a stand-in `gh`, and for the gate a throwaway git repository with a local bare "origin" and the Wikidata, OpenAlex and Crossref stand-ins | Calling Claude Code (arguments, events, limits, the login check and an API key), reading pages and quotes, every mechanical check, retries and their bound, the reviewer's view, usage thresholds, the audit log, the evaluation score, and a whole run to a draft pull request with a row dropped at the gate; for route sources, made-up routes in a copy of the repository: editing every route file without moving anything else, the terms and passages found, both kinds of proposal and their checks, and a run to a draft pull request whose merge makes the queue say a quote is ready; for re-checks, made-up merged facts (an ore row, a quote, a reference whose page changed): code's checks, the reviewer only when asked, choosing by prompt version, no data changed, and failures reported once as issues. No network and no Claude usage. |
| Report tests (`pipeline/tests/test_reports.py`) | Made-up report issues in GitHub's shape, one of them a pull request (`fixtures/github-report-issues.json`), served by a local stand-in for the issues API (`github_endpoint` in `conftest.py`) | Reading the form's fields, keeping no reporter or text, leaving pull requests out, and reports first in the queue, one item per fact. |
| Withdrawal tests (`packages/core/tests/test_withdraw.py`) | Made-up routes, ore rows and run summaries in a copy of the data | Each kind of withdrawal changes only its fact and is recorded; a person's fact, a missing one and a run with no summary are refused; validate refuses a withdrawn quote put back; the command's messages. |
| Wikidata tests (`pipeline/tests/test_wikidata.py`) | 4 real Wikidata statements (`pipeline/tests/fixtures/wikidata-sample.csv`) and every crosswalked item's label, description and formula (the committed backup, `snapshots/wikidata_items/`), served by a local stand-in for the SPARQL endpoint (`wikidata_endpoint` in `conftest.py`) | The query, the snapshot, precedence, overrides (and stale ones) and suppressions, with no network. |

The built graph has the curated graph's documents in the same order, except that each thing's quantities are the values `graph_facts` chose, followed by the upstream nodes. `pipeline/tests/test_build.py` checks both. Copies of the data made for tests (`data_copy`) link to the real cold backups; a test that needs a dataset missing replaces the link with a copy that leaves it out.

## Files and configuration

| Path | What |
|---|---|
| `build/upstream/<dataset>/` | Downloaded snapshots: the data as Parquet, and `snapshot.json`. Without them, the build uses the cold backups. |
| `snapshots/<dataset>/` | The cold backups, in git, with a README of their licenses. Refreshed by `capabilities backup`. |
| `build/warehouse.duckdb` | The warehouse: the raw tables and the staging views. |
| `build/graph/` | The artifact the app reads. |
| `build/dbt/target/`, `build/dbt/logs/dbt.log` | dbt's compiled SQL, run results, and log. Dagster runs each get a folder under `target/`. |
| `pipeline/dbt/dbt_project.yml` | Project settings: staging models are views, marts are external Parquet, each layer's Dagster group, and anonymous usage statistics are off. |
| `pipeline/dbt/profiles.yml` | The DuckDB connection: the warehouse path, and `external_root` (where external models are written), both from `$CAPABILITIES_BUILD_DIR`, and the `spatial` extension. DuckDB downloads the extension the first time it loads it. |
| `pipeline/pyproject.toml`, `[tool.dg]` | Where the `dg` command finds the Dagster definitions. |
| `audit/agents.duckdb`, `audit/runs/<run>.json`, `audit/rechecks/<id>.json` | The agents' append-only audit log, every run's summary, and every re-check's. Ignored by git. `$CAPABILITIES_AUDIT_DIR` puts them elsewhere (tests do). |
| `data/agent_runs/<run>.json` | The summary of a run whose proposals are in a pull request, committed with them. Withdrawing and re-checking read it. |
| `data/withdrawals.csv` | Agents' facts withdrawn, with what they said and why. |
| `.github/ISSUE_TEMPLATE/report.yml` | The report form the app's links open. |
| `pipeline/src/capabilities_pipeline/agents/prompts/`, `evaluation/` | The agents' prompts, and the evaluation set. |

The build directory is, in order: `--build-dir`, then `$CAPABILITIES_BUILD_DIR`, then `build/` in the repository. `build/` is ignored by git. Tests always use a temporary directory.

## When a build fails

`BuildError` names the failing models or tests and points to `build/dbt/logs/dbt.log`. Common causes:

- **A data test failed**, for example two nodes share an id. The YAML files can each be valid on their own and still clash. Fix the data and rebuild.
- **No copy of a dataset** (`MissingSnapshot`): nothing downloaded and no cold backup. Download it with Dagster, or restore `snapshots/<dataset>/` from git.
- **A YAML syntax error.** The message names the file.
- **A crosswalk row names something that isn't a source**, or isn't in the graph (`crosswalk_maps_to_sources`, `relationships_...`).
- **An override names a thing that isn't in the Wikidata crosswalk, or a quantity not read from Wikidata** (`overrides_target_upstream_values`): correct the curated value in the thing's file instead.
- **A Wikidata value is in another unit than its quantity expects** (`wikidata_units_match`): add a conversion, or suppress the item.
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
cd pipeline && uv run dg launch --assets 'upstream/wikidata_quantities'   # just query Wikidata again
uv run capabilities backup                     # make newer downloads the cold backups in snapshots/ (then commit)
uv run capabilities queue                      # the curation queue: what to review next
claude auth status                             # agents run on this login: authMethod must be "claude.ai"
cd pipeline && uv run dg launch --job agent_curation --config-json '{"ops": {"curate": {"config": {"items": 10, "evaluate": true}}}}'   # an evaluation
cd pipeline && uv run dg launch --job agent_curation --config-json '{"ops": {"curate": {"config": {"items": 5}}}}'   # five ore candidates, to a draft PR
cd pipeline && uv run dg launch --job agent_curation --config-json '{"ops": {"curate": {"config": {"task": "route_sources", "items": 40, "find_only": true}}}}'   # what each queued route would be offered, for none of the plan
cd pipeline && uv run dg launch --job agent_curation --config-json '{"ops": {"curate": {"config": {"task": "route_sources", "items": 10}}}}'   # ten routes, to a draft PR
cd pipeline && uv run dg launch --assets 'upstream/github_reports'   # readers' open reports, for the queue
cd pipeline && uv run dg launch --job agent_recheck --config-json '{"ops": {"recheck": {"config": {"runs": ["ore-20261125-222345"]}}}}'   # check a run's merged facts again, free
cd pipeline && uv run dg launch --job agent_recheck --config-json '{"ops": {"recheck": {"config": {"every_fact": true, "reviewer": true, "report_failures": true}}}}'   # every fact, with the reviewer (uses the plan), reporting failures
uv run capabilities withdraw reference <route> --citation "<citation>" --reason "<why>" --report <issue>   # take an agent's fact out
```

To look at the output from Python:

```python
import duckdb
duckdb.sql("select node_type, count(*) from 'build/graph/graph_nodes.parquet' group by all").show()
duckdb.sql("""
    select source_id, state, count(*) from 'build/graph/source_occurrences.parquet'
    where id is not null group by all order by all
""").show()
duckdb.sql("select id, layer, value, curated_value, disagrees from 'build/graph/graph_facts.parquet' order by all").show()
```

## Planned changes

| Milestone | Change to the pipeline |
|---|---|
| M1 | Done: Dagster runs the build; MRDS, the MRDS crosswalk and `source_occurrences`, served by `GET /api/occurrences/{id}` to the map; Wikidata's quantities through a crosswalk, overrides, suppressions and `graph_facts`; every dataset required, with cold backups; upstream ore minerals as nodes, roasting, and `curation_queue`. Pleiades' ancient mines and quarries as occurrences of sources and ore classes, and `unmatched_place` in the queue (slice 4c, [ADR 0046](../adr/0046-place-ancient-mines-and-quarries-from-pleiades.md)). |
| M2 | Done: every cited work looked up in OpenAlex and Crossref, and every cited link checked (`upstream/reference_candidates`); the `reference_checks` mart; the reading queue (`unread_reference`) ([ADR 0047](../adr/0047-check-citations-against-openalex-and-crossref.md)). |
| M3 | Slice 3a: the agent curation job on ore candidates, its mechanical checks, gate, draft pull requests and append-only audit log, on a Claude subscription ([ADR 0048](../adr/0048-run-agents-through-claude-code-on-a-claude-subscription.md)). Slice 3b: agent runs take a task, and the second quotes sources for routes whose references are all unverified ([ADR 0049](../adr/0049-have-agents-quote-sources-for-unverified-routes.md)). Slice 3c: readers' reports as GitHub issues, queued first; withdrawing agents' facts into `data/withdrawals.csv`; re-checking merged facts by run, prompt or model, only when an admin starts it ([ADR 0050](../adr/0050-report-withdraw-and-recheck-agent-facts.md)). |
| M5 | Raw and staging tables move to Apache Iceberg with an Apache Polaris catalog; the build still exports this artifact for the app. |

Each change updates this page in the same pull request ([ADR 0039](../adr/0039-keep-architecture-docs-and-diagrams-current.md)).
