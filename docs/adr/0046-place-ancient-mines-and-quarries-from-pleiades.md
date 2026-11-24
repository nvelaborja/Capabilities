# 0046. Place ancient mines and quarries from Pleiades

- **Status:** Proposed
- **Date:** 2026-11-24

## Context

The map shows where materials are found ([0042](0042-show-where-things-are-found-on-a-maplibre-map.md)). Its places come from USGS MRDS ([0041](0041-place-sources-with-mrds-deposits-through-a-crosswalk.md)): modern records, most of them in the United States. For history, the places that matter are the ones worked in antiquity, and the plan names Pleiades for them.

Pleiades is a community-built gazetteer of ancient places (CC BY 3.0). Every morning it publishes all its places as one CSV (`pleiades-places-latest.csv.gz`, 6.5 MB). On 2026-11-24 it held 42,544 places, 830 of them typed as a mine (`mine-2`), a quarry (`quarry`) or the deprecated "mine, quarry" (`mine`, from a Barrington Atlas symbol that stands for either). For each it gives a title and description, a representative point and how precise it is (709 precise, 106 rough, 11 placed by a related place, 4 unlocated), the years it is attested from and to, and the named periods (about 40 of them: Archaic, Roman, Late Bronze Age Iran…).

What was worked isn't a field of its own. Most places carry it in `tags`, taken from the Digital Atlas of the Roman Empire: copper 115, gold 109, limestone 94, marble 78, iron 70, lead 68, silver 67, granite 14, tin 7, flint 1. A few name it only in the title or description ("Bronze Age copper mine reused as a sanctuary"). A copper mine doesn't say which ore was mined.

The user's view: where a material was found is among the least important things in the graph; the app's questions don't depend on it, and "this material was nearby and could have been used" is enough. Matching needn't be perfect.

## Decision

**Pleiades is a required dataset** ([0044](0044-require-every-upstream-dataset-with-cold-backups-in-git.md)): a Dagster asset, `upstream/pleiades_places`, downloads the daily dump, kept as published (every place, every column, as text), with a cold backup in `snapshots/pleiades_places/` (5.1 MB).

**Mines and quarries match our sources by rules**, a hand-kept table like the MRDS crosswalk: `data/crosswalks/pleiades_sources.csv`, one row per rule: a target, the kind of place (`mine` or `quarry`; the deprecated type counts as both) and a word. A place matches when it is of that kind and names the word as a tag, or whole in its title or description. "Iron Age" is removed before matching: it is a date, not iron (Almyras, a copper site, has remains "dated to the Iron Age"). A wrong match is suppressed in `data/suppressions/suppressed_records.csv` (dataset `pleiades`). The first rules:
- quarries naming granite or limestone: the granite and limestone outcrops;
- mines naming flint: flint deposits;
- mines naming copper, iron or tin: the ore class (copper ore, iron ore, tin ore), since which ore isn't recorded. Copper mines also belong to copper sulphide ore, whose members (chalcopyrite) aren't in copper ore.

**A class can have places.** An occurrence's `source_id` is a source or an ore class. A material extracted from the ground is shown at its own sources' places and at its classes' places, which the map marks "Copper ore mined here; which ore isn't recorded". The reasoner doesn't read places yet, so nothing else changes.

**A Pleiades place is worked, with the years it is attested.** Occurrences gain `attested_from`, `attested_to` (years, negative BC), `periods` (Pleiades' keys) and `approximate` (true unless Pleiades calls the location precise). Rough and related locations are kept, marked "Approximate location". `worked_by_year` stays empty for Pleiades: the year a place was certainly worked by is the end of its earliest attested period, which needs Pleiades' period vocabulary, another dataset. M4, which compares places with a profile's date, brings it in if it needs it.

**Unmatched mines and quarries are queued last.** The curation queue gains `unmatched_place`: located mines and quarries no rule matches, one item per material they name (gold, marble…) and one for those naming none, ranked by count. It is ordered after every other kind: placing a material matters least to the app's questions.

## Consequences

- With the snapshot of 2026-11-24, 290 Pleiades places match, 421 times (a copper mine is a place of two classes): copper 118, limestone 94, iron 68, granite 14, tin 8, flint 1. Occurrences rise from 35,311 to 35,732.
- The queue gains 35 `unmatched_place` items: 236 places naming no material, then gold (100), marble (77), lead (37), silver (33), sandstone (19)…
- Malachite's map adds 118 ancient copper mines, chalcopyrite's the same through copper sulphide ore, hematite's 68 iron mines.
- The map credits each dataset with its own note; Pleiades' says CC BY 3.0. CREDITS.md and `snapshots/README.md` credit Pleiades.
- The repository grows by about 5 MB, and by about as much each time the backup is refreshed. Pleiades changes daily, but a backup is refreshed only on purpose ([0044](0044-require-every-upstream-dataset-with-cold-backups-in-git.md)), so rarely.
- Pleiades encourages citing a numbered release for static scholarly work. We use the daily dump and record the day retrieved, as for the other datasets.
- Some matches will be wrong, and some places are only roughly located. That is accepted: the map says so, and suppressions fix what someone notices.

## Alternatives considered

- **List each place by hand** (about 840). Exact, but far more work than where a material was found is worth to the app.
- **Match on tags only.** Simpler, but misses places that name their material only in words (Chale Ghar 1, Temesa, As Muradellas).
- **Attach copper mines to one mineral (malachite)**, or to a generic "copper ore deposit" source. The first claims what the record doesn't say; the second needs a source no route extracts from.
- **Show class-level places only when the class itself is selected.** Tidier maps, but a reader looking at malachite wouldn't see the ancient copper mines at all. The user chose every member; it can change if the maps look crowded.
- **Leave out rough locations.** Cleaner points, but it drops 106 real attestations; marking them approximate keeps both.
- **The GIS package of `pleiades.datasets`** (separate CSVs with each period's years). It gives the period years, but it is updated less often and needs several files joined; the daily dump has everything the map needs.
