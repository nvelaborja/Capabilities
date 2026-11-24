# Data pipeline

Reference for how the graph is built: inputs, stages, tables, outputs, checks and commands. The diagrams are at `/architecture/`: `pipeline_overview` shows the build as stages in series (1a curated layer and 1b download, 2 load, 3a transform and 3b test, 4 publish, 5 serve), and `pipeline` shows every input, table and output in the same stages, with green lineage arrows for where the data goes next. For background on the tools, see [DuckDB](technologies/duckdb.md), [dbt](technologies/dbt.md), [Parquet](technologies/parquet.md) and [Dagster](technologies/dagster.md). Decisions: [ADR 0034](../adr/0034-build-the-graph-from-upstream-datasets-and-a-curated-layer.md) (a built graph from a curated layer and, later, upstream datasets) [ADR 0038](../adr/0038-serve-the-app-from-a-built-graph-artifact.md) (the artifact the app reads), [ADR 0040](../adr/0040-orchestrate-the-build-with-dagster.md) (Dagster, and the quick build without it), [ADR 0041](../adr/0041-place-sources-with-mrds-deposits-through-a-crosswalk.md) (MRDS deposits as source occurrences) [ADR 0043](../adr/0043-take-quantities-from-wikidata-with-upstream-first-and-overrides.md) (quantities from Wikidata, upstream first, with overrides) [ADR 0044](../adr/0044-require-every-upstream-dataset-with-cold-backups-in-git.md) (every dataset required, with cold backups in git) and [ADR 0045](../adr/0045-bring-ore-minerals-in-from-upstream-roast-sulphides-and-queue-the-gaps.md) (ore minerals from upstream as nodes, and the curation queue). Spatial work uses [DuckDB spatial and GeoParquet](technologies/duckdb-spatial-and-geoparquet.md); Wikidata is queried with [SPARQL](technologies/wikidata-and-sparql.md).

## Summary

| | |
|---|---|
| **Inputs** | The curated layer: `data/**/*.yaml` (quantities, things, verbs, routes, profiles, overrides), `data/crosswalks/*.csv`, `data/suppressions/*.csv`, `examples/**/*.yaml` (jobs) and `schema/*.json`. A copy of every upstream dataset (USGS MRDS, Wikidata's quantity statements and item descriptions, Pleiades' places, and what OpenAlex and Crossref hold for each cited work): the latest download in `build/upstream/` or the cold backup in `snapshots/`, whichever is newer. Every dataset is required ([ADR 0044](../adr/0044-require-every-upstream-dataset-with-cold-backups-in-git.md)). |
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

The `upstream/reference_candidates` asset looks up every work the curated layer cites ([ADR 0047](../adr/0047-check-citations-against-openalex-and-crossref.md), [OpenAlex and Crossref](technologies/openalex-and-crossref.md)). `cited_works` in `citations.py` reads every reference in the YAML and the ore crosswalk's (rows not rejected); a work is its citation text, so a book cited by eleven routes is looked up once. A work with a DOI is looked up by it in OpenAlex (`/works/doi:<doi>`, free) and Crossref (`/works/<doi>`). A work with a year in brackets is searched for: OpenAlex by its title (`search=`, what follows the year up to the first full stop, without an edition or "as summarized in"), Crossref by the whole citation (`query.bibliographic=`). Five candidates each are kept; a lookup that finds nothing is one row with no candidate. A web page or undated work isn't searched. Then every cited URL is requested once and its HTTP status kept. Requests pause between each other to stay inside Crossref's anonymous limit (one search a second) and OpenAlex's (ten a second); a 429 or a server error is retried three times, then fails, and the download falls back to the cold backup. No key is needed; `OPENALEX_API_KEY`, if set, is sent. Only bibliographic fields are kept, never an abstract. The result, `reference_candidates.parquet`, has the columns `citation`, `service` (`openalex`, `crossref` or `link`), `lookup` (`doi`, `search` or `link`), `query`, `status`, `rank`, `record_id`, `doi`, `title`, `year`, `authors`, `type`, `oa_url`, `pdf_url` and `score` (Crossref's relevance). Its `snapshot.json` adds `crossref_url`, the number of `works` and how many were `searched`. On 2026-11-24: 43 works, 27 searched or looked up by DOI, 24 links; 242 rows, in about a minute and a half.

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

**`raw.ore_minerals`**: the crosswalk `data/crosswalks/ore_minerals.csv`: `id`, `wikidata`, `mrds_ore`, `class`, `mined_like`, `citation`, `url`, `supports`, `notes` ([data format](../data-format.md)).

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
- `raw.ore_minerals`: `id` is unique; `wikidata` and `mrds_ore` are unique and not null; `class` is one of the ore classes or `none`; `citation` and `supports` are not null.
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

Each node's provenance is `{"layer": "upstream", "crosswalk": "data/crosswalks/ore_minerals.csv", ...}` with what it came from: the mineral `"dataset": "wikidata", "record": <Q id>, "url": ...`; the deposit `"dataset": "mrds", "record": "deposits listing <MRDS name> as an ore mineral"`; the route `"copied_from": <template>`.

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
| `kind` | `ore_candidate`, `extracted_without_route`, `source_without_places`, `route_unverified`, `upstream_disagreement`, `stale_override`, `unread_reference` or `unmatched_place`. |
| `subject`, `label` | What the item is about: an MRDS ore name (lower case), a node or fact id, or a work's check id (`ref-…`, labelled with its citation), and how to show it. |
| `detail` | What is missing, and what to do. |
| `priority` | For ore candidates, the number of MRDS deposits of copper, iron or tin listing the mineral as an ore; for unread references, the number of routes citing the work; for unmatched places, the number of places; otherwise null. |
| `evidence` | JSON: the deposits and metals for a candidate, the values behind a disagreement, and so on. |

An ore candidate is a mineral listed on at least 20 such deposits and not yet reviewed: in neither the ore crosswalk nor `mrds_sources`. An unmatched place group is the located Pleiades mines and quarries that no rule matches and none suppressed, by a material they name (gold, marble…), or naming none. They come last, after every other kind: where a material was found matters least to the app's questions ([ADR 0046](../adr/0046-place-ancient-mines-and-quarries-from-pleiades.md)). An unread reference is a work not yet verified everywhere it is cited: the reading queue, ranked by how many routes cite it, saying what the check found and offering a free copy ([ADR 0047](../adr/0047-check-citations-against-openalex-and-crossref.md)). Tests: `id` unique and not null; `kind` one of the eight; `detail` not null. With the 2026-11-24 snapshots there are 264 items: 135 ore candidates (galena first, on 6,326 deposits), 49 routes with only unverified references, 2 sources with no places, 43 unread references (Craddock and Tylecote first, 11 routes each), and 35 groups of unmatched places (236 naming no material, then gold, 100). `uv run capabilities queue` prints them.

**`stg_references__cited`** (view). Every reference in the graph, one row per use: `node_id`, `node_type`, `citation` (trimmed), `doi`, `url` and `status`. It walks each document with `json_tree`, so a reference nested anywhere (a route's, a profile item's, an override's) is found: in the curated documents, example jobs included, and in the upstream nodes (an ore mineral's reference, and those a copied mining route keeps).

**`stg_references__candidates`** (view). The candidates of `raw.reference_candidates`, typed (`rank`, `year` integers; `score` a double; `doi` lower case), with `title_words`, `main_title_words` (before a colon) and `plain_authors` for comparing. Link rows are left out.

**`reference_checks`** (mart, written as Parquet). Every cited work, checked ([ADR 0047](../adr/0047-check-citations-against-openalex-and-crossref.md)). From the citation it reads the year in brackets, the title after it (up to the first full stop, without an edition), and the first author's surname at the start. A candidate's title score is the `word_overlap` of the two titles, whole or before a colon, whichever is higher. A candidate is the work when its title scores at least 0.8, it isn't a review, its authors include the surname, and its year is the cited year give or take one (another edition is only possible). A review (`book-review`, `review`) with the title, from the cited year to five years after, is a review of it. A title scoring at least 0.5 is a possible match. The best candidate is the work, else a review, else a possible match, by title score, closeness of year, OpenAlex first, then rank.

| Column | Meaning |
|---|---|
| `id` | `ref-` and the first 12 hex digits of the citation's MD5. |
| `citation`, `doi` | The work, and the DOI cited for it (the largest, if uses disagree; `citations.py` makes the same choice). |
| `statuses`, `verified` | The statuses its uses give; `verified` when every use is verified. |
| `cited_by`, `routes` | The nodes citing it, and how many are routes (copied mining routes included). |
| `result` | `found`, `review_found`, `possible`, `not_found`, `doi_disagrees` (the DOI cited leads to a different work), `not_searched` (a web page or undated work) or `not_checked_yet` (cited since the last download). |
| `note` | Why, in words: what differs for a possible match ("the year differs (cited 1992, found 1978): perhaps another edition"), and the meaning of the other results. |
| `match_service`, `match_id`, `match_doi`, `match_title`, `match_year`, `match_authors`, `match_type`, `title_score` | The record matched, for a work found, a review, a possible match or a wrong DOI's work. |
| `free_copy` | OpenAlex's PDF link, else its best open-access link, for the record matched or another OpenAlex record with its DOI. |
| `links` | JSON: each URL cited for the work, its `status` and `state`: `works` (2xx or 3xx), `refused` (401, 403 or 429: the site turns automated requests away) or `broken`. |
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
| `upstream/mrds_deposits`, `upstream/wikidata_quantities`, `upstream/wikidata_items`, `upstream/pleiades_places`, `upstream/reference_candidates` | upstream | Download (`fetch_or_fall_back` in `upstream.py`), or the cold backup when the network fails. Their URLs come from the `downloads` resource (`openalex_url` and `crossref_url` for the references), which tests point at a local zip or gzip, local stand-ins for the SPARQL endpoint and for OpenAlex and Crossref, or a port that refuses connections. | None |
| `raw/curated_documents`, `raw/mrds_sources`, `raw/wikidata_things`, `raw/ore_minerals`, `raw/suppressed_records`, `raw/pleiades_sources`, `raw/mrds_deposits`, `raw/wikidata_quantities`, `raw/wikidata_items`, `raw/pleiades_places`, `raw/reference_candidates`, `raw/upstream_snapshots` | raw | Load (`load_inputs`): one multi-asset, since the fingerprint is taken once before anything is read. The keys are the dbt sources' keys, so lineage runs into dbt. | The source tests above |
| `stg_curated__documents`, `stg_curated__quantities`, `stg_curated__overrides`, `stg_curated__quantity_properties`, `stg_crosswalk__wikidata_items`, `stg_wikidata__items`, `stg_ore_minerals__nodes`, `stg_mrds__deposits`, `stg_wikidata__quantities`, `stg_pleiades__workings`, `stg_references__cited`, `stg_references__candidates` | staging | dbt views | Their tests above |
| `graph_facts`, `graph_nodes`, `source_occurrences`, `reference_checks`, `curation_queue` | marts | dbt marts, written as Parquet | Their tests above |
| `graph_manifest` | marts | Publish (`write_manifest`) | None |

Every dbt test that belongs to one model or source is an asset check (94 today). Tests that compare two tables, such as `crosswalk_maps_to_sources`, still run in `dbt build` but aren't attached to an asset. "Materialize all" downloads every dataset again, and looks up every cited work; to rebuild from the snapshots you have, select everything except the `upstream` group. Loading the definitions runs `dbt parse` first, so the asset list always matches the dbt project. dbt's files for each Dagster run go in `build/dbt/target/<run>/`.

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
| Citation tests (`pipeline/tests/test_citations.py`) | What OpenAlex and Crossref answered on 2026-11-24 (the committed backup, `snapshots/reference_candidates/`), served by a local stand-in for both (`scholarly_endpoint` in `conftest.py`), with links answered from the backup too (`lookups_offline`) | A download gives back the backup unchanged; each work looked up once; DOIs, searches and web pages; every result, a wrong DOI, a citation added since the lookup, and the reading queue, with no network. |
| Ore mineral tests (`pipeline/tests/test_ore_minerals.py`) | The built graph from the cold backups | The upstream nodes, roasting, and the queue. |
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
| M3 | The agent curation stage and its append-only audit log. |
| M5 | Raw and staging tables move to Apache Iceberg with an Apache Polaris catalog; the build still exports this artifact for the app. |

Each change updates this page in the same pull request ([ADR 0039](../adr/0039-keep-architecture-docs-and-diagrams-current.md)).
