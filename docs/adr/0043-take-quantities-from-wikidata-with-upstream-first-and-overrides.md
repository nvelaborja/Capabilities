# 0043. Take quantities from Wikidata, upstream first, with overrides

- **Status:** Accepted; keeping curated values that match upstream superseded by [0044](0044-require-every-upstream-dataset-with-cold-backups-in-git.md)
- **Date:** 2026-11-23
- **Supersedes:** in part, [0034](0034-build-the-graph-from-upstream-datasets-and-a-curated-layer.md) (the rule that the curated layer always wins)

## Context

[0034](0034-build-the-graph-from-upstream-datasets-and-a-curated-layer.md) makes the graph a built product: upstream datasets plus a curated layer that maps, overrides, suppresses and annotates. It also says that, field by field, "the curated layer always wins". [0041](0041-place-sources-with-mrds-deposits-through-a-crosswalk.md) brought in the first upstream dataset, MRDS, for where sources are found. Nothing upstream yet gives the graph's own values.

Wikidata (CC0) holds the properties the reasoner compares. On 2026-11-23 it had 6,317 mineral species, 936 of them with a Mohs hardness (property P1088), each stored as a value with lower and upper bounds. Our things use two quantities: Mohs hardness on 21 of them, and fracture toughness on 2. Of the 15 materials we can match to a Wikidata item, 11 have a hardness there. It matches ours exactly for 7 (hematite, malachite, cassiterite, diamond, limestone, native copper and tin). It differs for 4:

| Thing | Ours | Wikidata |
|---|---|---|
| Granite | 6–7 | 5–7 |
| Limonite | 4–5.5 | 1.5–6 |
| Copper | 2.5–3 | 3 |
| Tin bronze | 3–4 | 3 (bronze) |

The curated values are early and lightly sourced: most cite one textbook, unverified. The upstream datasets are the master set for what they cover. So during this early phase, an upstream value should be trusted over our own, and an override should be how we disagree with upstream, not how we keep our first guesses.

## Decision

**A Wikidata crosswalk.** `data/crosswalks/wikidata_things.csv` matches our things to Wikidata items (`id`, `wikidata`, `notes`), one item per thing, with why in `notes`. A match is added only when the item is the same thing; a thing with no clear item stays unmatched (quartz sand, hardened steel). Our ids stay our own (0034).

**Quantities name their Wikidata property.** A quantity's `wikidata` field (`hardness_mohs` has `wikidata: P1088`) says which property holds it.

**A snapshot of what we ask for.** The Dagster asset `upstream/wikidata_quantities` sends one SPARQL query to `query.wikidata.org` for every property our quantities name, on every crosswalked item. It takes only best-ranked statements, which Wikidata treats as current. The result is kept unchanged as Parquet, as MRDS's is, and `snapshot.json` records the query itself.

**Precedence: an override, then upstream, then curated.**
- A thing's value of a quantity is the upstream value when there is one. A statement with bounds is the range `[lower, upper]`; one without is a single number. Several best-ranked statements become one range, as [0007](0007-compare-ranges-with-three-answers.md) handles ranges.
- A curated value that disagrees is not dropped. The build keeps it beside the upstream value and marks the disagreement.
- An **override** (`data/overrides/<id>.yaml`) replaces an upstream value we believe is wrong. It names the thing, the quantity, our value, the upstream value it replaces, the reason and at least one reference (`schema/override.schema.json`). If upstream later changes, the override is marked stale for review. An override may only replace a value that comes from upstream; a curated-only value is edited where it is.
- A **suppression** (`data/suppressions/suppressed_records.csv`: `dataset`, `record_id`, `reason`) leaves an upstream record out entirely: a Wikidata item, or an MRDS deposit. It is for records that don't belong, not unwelcome history (0034).

**Facts with provenance.** A new mart, `graph_facts.parquet`, has one row per thing and quantity: the value used, which layer it came from, the upstream record (dataset, item, link, retrieval date), the curated value, whether they disagree, and the override, if any. `graph_nodes` carries the chosen values in each document, so the reasoner uses them without knowing where they came from.

**Shown in the app.** Under each value in the detail pane:
- an upstream value names its dataset and record, links to it, and says when it was retrieved;
- when our curated value differs, it is shown too ("Our curated value was 6–7 Mohs");
- an override says "Overridden", what upstream says, the reason and its sources, marked by a rule beside it, never by colour alone ([0019](0019-desktop-first-mobile-ready.md));
- a curated value points to the sources listed below it.

## Consequences

- Every quantity value in the graph has provenance, as 0034 asked.
- With the 2026-11-24 snapshot, granite's hardness is 5–7, limonite's 1.5–6, copper's 3 and tin bronze's 3. The worked examples in `examples/README.md` give the same answers with and without the snapshot, checked by running `need`, `explore` and `check` on both builds.
- The four disagreements were settled when this was accepted: the curated values of granite, limonite, copper and tin bronze now match Wikidata, and cite the Wikidata item instead of the work that backed the old value. The curated values stay rather than being deleted, so a build without a Wikidata snapshot (as in CI) gives the same answers. Later disagreements show in the app and in `graph_facts` (`disagrees`), and go to the curation queue (milestone 1, slice 4b).
- Answers can change when Wikidata changes. The snapshot is what makes a build reproducible; downloading again is a deliberate step, and `graph_facts` shows what moved.
- The build directory's format version is now 3, because of the new file.
- Wikidata is edited by anyone. Best-ranked statements, a snapshot, visible provenance and overrides are the guard against a bad edit, not trust in any one value.
- Only quantities are taken from upstream. Labels, descriptions, classes and routes stay curated; upstream nodes join the graph in slice 4b.

## Alternatives considered

- **Keep "the curated layer always wins" (0034).** It protects the reasoning from upstream mistakes, but it makes our least-sourced values the hardest to replace, and it leaves upstream data unused wherever we already wrote something.
- **Use the curated value and only report the disagreement.** Safer for answers, but it delays using upstream data until each value is reviewed by hand, which is the work the curation queue and agents (M3) are for.
- **Merge disagreeing values into one wider range.** 0034 does this between upstream sources. Between curated and upstream it would hide which one we trust, and widen every range we had doubts about.
- **Download Wikidata's full dump, or every mineral.** The full JSON dump is 157 GB compressed (2026-11-23). Every mineral (6,317) is more than the graph uses today; slice 4b decides which upstream minerals become nodes. Asking only for crosswalked items keeps the snapshot to a few rows and one query.
- **Overrides in the crosswalk CSV.** One file, but a reason and references don't fit in a CSV cell, and overrides need the same schema validation and citation rules ([0008](0008-record-the-basis-of-every-number.md)) as the rest of the curated layer.
