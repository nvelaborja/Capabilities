# Wikidata and SPARQL

## What it is

**Wikidata** is Wikimedia's free knowledge base: structured facts about over a hundred million items, edited by anyone, and published under CC0, so anyone can reuse them for anything. Where Wikipedia has an article, Wikidata has an **item** with **statements**: "granite: Mohs hardness 5 to 7".

**SPARQL** is the query language for RDF, data stored as subject–predicate–object triples. Wikidata publishes its data as RDF, and the **Wikidata Query Service** at `query.wikidata.org` answers SPARQL queries over all of it.

## How it works

**Items, properties and statements.** Every item has an id starting with Q (granite is `Q41177`), and every property one starting with P (Mohs hardness is `P1088`). A statement says that an item has a value of a property. One item can have several statements of the same property: two sources might give different hardnesses.

**Values with bounds and units.** A quantity value is more than a number. It has an **amount**, an optional **lower bound** and **upper bound**, and a **unit**, itself an item. Granite's hardness is amount 6, bounds 5 and 7, unit `Q199` ("1", for a number with no unit). The bounds are how Wikidata writes a range.

**Ranks.** Each statement is **preferred**, **normal** or **deprecated**. The **best-ranked** statements of a property are the preferred ones if there are any, else the normal ones; deprecated statements are kept as a record of what used to be believed, and are never best. Best-ranked statements are what Wikidata treats as current.

**Qualifiers and references.** A statement can carry qualifiers (when it was true, under what conditions) and references (where it came from). We don't use them yet.

**RDF and its prefixes.** In the query service, each fact is one or more triples, and prefixes name the parts:

| Prefix | Means | Example |
|---|---|---|
| `wd:` | an item | `wd:Q41177` (granite) |
| `wdt:` | the "truthy" value: best rank, amount only | `wd:Q41177 wdt:P1088 6` |
| `p:` | from an item to a statement node | `wd:Q41177 p:P1088 ?statement` |
| `ps:` | from a statement to its simple value | `?statement ps:P1088 6` |
| `psv:` | from a statement to its full value node | `?statement psv:P1088 ?value` |
| `wikibase:` | Wikidata's own vocabulary | `wikibase:quantityLowerBound`, `wikibase:BestRank` |

The short `wdt:` path is handy but drops the bounds, so a range would come back as one number. Reading bounds needs the long path: item, `p:`, statement, `psv:`, value node, then `wikibase:quantityAmount`, `quantityLowerBound`, `quantityUpperBound` and `quantityUnit`.

**SPARQL in five ideas.**
- A query is a pattern of triples with variables (`?item`), and the answer is every way of filling the variables so the pattern is in the data.
- `SELECT` picks the variables to return; `VALUES` fixes a variable to a list (`VALUES ?entity { wd:Q41177 wd:Q103223 }`).
- `OPTIONAL { … }` keeps a row when part of the pattern is missing, like a left join. Without it, a statement with no bounds would vanish.
- `UNION` joins alternatives; `BIND` sets a variable (`BIND("P1088" AS ?property)`); `FILTER` drops rows.
- `STRAFTER(STR(?entity), "/entity/")` turns a full IRI into a bare id, which keeps the result small and readable.

**The query service.** It accepts a query by HTTP GET or POST and returns JSON, XML, CSV or TSV, chosen by the `Accept` header. A query on the public endpoint may run for at most 60 seconds. Wikimedia's User-Agent policy asks clients to send a user agent that identifies them.

## How we use it

Wikidata gives the graph its quantity values ([ADR 0043](../../adr/0043-take-quantities-from-wikidata-with-upstream-first-and-overrides.md)):

1. `data/crosswalks/wikidata_things.csv` matches our things to Wikidata items, with why, and `data/crosswalks/ore_minerals.csv` names the ore minerals that join the graph from Wikidata ([ADR 0045](../../adr/0045-bring-ore-minerals-in-from-upstream-roast-sulphides-and-queue-the-gaps.md)). A quantity's `wikidata` field says which property holds it and the unit its values must be in (`hardness_mohs`: `P1088`, unit `Q199`).
2. The Dagster asset `upstream/wikidata_quantities` builds one SPARQL query from those (`quantities_query` in `upstream.py`), POSTs it to `query.wikidata.org/sparql`, asks for CSV, and keeps the result unchanged as Parquet. `snapshot.json` records the query, so a snapshot says exactly what was asked.
   A second asset, `upstream/wikidata_items`, asks for the same items' English labels and descriptions and their chemical formulas (P274), which name and describe the ore minerals.
3. `uv run capabilities backup` makes the snapshots the cold backups in `snapshots/wikidata_quantities/`, in git, so every build has it ([ADR 0044](../../adr/0044-require-every-upstream-dataset-with-cold-backups-in-git.md)).
4. dbt types the statements (`stg_wikidata__quantities`), checks their units (`wikidata_units_match`) and chooses each thing's value in `graph_facts`: an override, then Wikidata, then our curated value, which we keep only where Wikidata has none. The detail pane shows where each value came from, with a link to the item.

The query, for the crosswalked items and every property our quantities name:

```sparql
SELECT (STRAFTER(STR(?entity), "/entity/") AS ?item) ?property ?amount ?lower ?upper
       (STRAFTER(STR(?unitEntity), "/entity/") AS ?unit)
WHERE {
  VALUES ?entity { wd:Q103223 wd:Q41177 … }
  { ?entity p:P1088 ?statement . ?statement psv:P1088 ?value . BIND("P1088" AS ?property) }
  ?statement a wikibase:BestRank .
  ?value wikibase:quantityAmount ?amount ; wikibase:quantityUnit ?unitEntity .
  OPTIONAL { ?value wikibase:quantityLowerBound ?lower }
  OPTIONAL { ?value wikibase:quantityUpperBound ?upper }
}
ORDER BY ?item ?property ?amount
```

Why Wikidata: it is CC0, so it fits our non-commercial licensing without conditions ([ADR 0037](../../adr/0037-license-the-project-for-non-commercial-use-only.md)); it has the properties the reasoner compares, with ranges; and its ids are the common join key between datasets. Why one targeted query rather than the dump: the full JSON dump is 157 GB compressed (2026-11-23), and we need a few dozen values.

## Where it lives

| What | Where |
|---|---|
| The crosswalk | `data/crosswalks/wikidata_things.csv` |
| Which property each quantity is read from, and in what unit | `wikidata:` in `data/quantities/*.yaml` |
| The cold backup | `snapshots/wikidata_quantities/` |
| The queries and the download | `WikidataQuantities`, `WikidataItems`, `quantities_query`, `items_query` in `pipeline/src/capabilities_pipeline/upstream.py` |
| The Dagster assets | `wikidata_snapshot`, `wikidata_items_snapshot` in `pipeline/src/capabilities_pipeline/assets.py` |
| Typing and choosing values | `pipeline/dbt/models/staging/stg_wikidata__quantities.sql`, `pipeline/dbt/models/marts/graph_facts.sql` |
| Tests, with no network | `pipeline/tests/test_wikidata.py`, the `wikidata_endpoint` fixture in `conftest.py`, `pipeline/tests/fixtures/wikidata-sample.csv` |

```bash
cd pipeline && uv run dg launch --assets 'upstream/wikidata_quantities'   # query Wikidata again
uv run capabilities build                                                 # use the new snapshot
python3 -c "import json; print(json.load(open('build/upstream/wikidata_quantities/snapshot.json'))['query'])"
```

To try a query by hand, paste it into [query.wikidata.org](https://query.wikidata.org/), which adds the prefixes for you.

## Things to know

- **Use `p:`/`psv:` for ranges.** `wdt:` returns only the amount; granite would read as 6, not 5–7.
- **Ask for best rank.** Without `?statement a wikibase:BestRank`, deprecated statements come back too.
- **Units are checked.** A value in another unit than the quantity's `wikidata.unit` fails the build, rather than be read unconverted.
- **Several best statements become one range** in `graph_facts`, from the lowest bound to the highest.
- **Anyone can edit Wikidata.** The snapshot keeps builds reproducible, the detail pane shows where each value came from, and an override is how we disagree. Downloading again is a deliberate step.
- **Match items carefully.** "Flint" has an item for the rock and another for a mineral; "copper" is the element (whose properties are the metal's) and also a colour. The crosswalk's `notes` say which one and why.
- **A generic user agent.** We send `dataset-snapshot/1.0` and make one small query per download. Wikimedia's policy asks for a user agent that identifies the client.
- **Labels are lower case.** Wikidata writes "azurite"; the build capitalises the first letter for a node's label.
- **Tests never call Wikidata.** They POST to a local stand-in that answers each query with a sample of real rows.

## Further reading

1. [Wikidata: Introduction](https://www.wikidata.org/wiki/Wikidata:Introduction): items, properties and statements.
2. [Wikibase data model primer](https://www.mediawiki.org/wiki/Wikibase/DataModel/Primer): values, qualifiers, references and ranks in detail.
3. [Help: Ranking](https://www.wikidata.org/wiki/Help:Ranking): preferred, normal and deprecated.
4. [Wikidata SPARQL tutorial](https://www.wikidata.org/wiki/Wikidata:SPARQL_tutorial): SPARQL from the ground up, on Wikidata.
5. [RDF dump format](https://www.mediawiki.org/wiki/Wikibase/Indexing/RDF_Dump_Format): what `p:`, `ps:`, `psv:` and `wikibase:BestRank` mean.
6. [Query Service user manual](https://www.mediawiki.org/wiki/Wikidata_Query_Service/User_Manual): endpoints, formats and limits.
7. [SPARQL 1.1 Query Language](https://www.w3.org/TR/sparql11-query/): the W3C standard.
8. [Property P1088, Mohs' hardness](https://www.wikidata.org/wiki/Property:P1088), and [Wikidata's licensing](https://www.wikidata.org/wiki/Wikidata:Licensing) (CC0 for the structured data).
9. [Wikimedia User-Agent policy](https://meta.wikimedia.org/wiki/User-Agent_policy).
