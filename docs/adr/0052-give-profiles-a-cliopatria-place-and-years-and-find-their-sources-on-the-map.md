# 0052. Give profiles a Cliopatria place and years, and find their sources on the map

- **Status:** Proposed
- **Date:** 2026-11-27

## Context

[0036](0036-place-sources-and-profiles-in-space-and-time.md) decided that profiles get a place and a time, and that a source's availability for a profile is computed from where its occurrences are and whether they were worked by then: yes, maybe ("present, not known to be worked by then"), or not in the area. It left the profile's place open (a polygon, a Pleiades place, or a Cliopatria polity), and distance for a later ADR. Occurrences now carry the year they are known to have been worked by ([0051](0051-write-dates-as-signed-years-and-date-workings-from-periods-and-curated-dates.md)).

What there was to build on (2026-11-27):

- **One profile**, `middle-kingdom-egypt`: a hand-picked list, with `period` ("c. 2050–1650 BCE") and `region` ("Nile valley") as free text.
- **Cliopatria** v0.2.2 (released 2026-11-25, CC BY 4.0): Seshat's borders of the world's polities from 3400 BCE to 2024 CE. One GeoJSON (177 MB, 47 MB zipped) in its GitHub repository, with releases tagged. 13,246 rows, 1,644 entities: each row is an entity's polygons for a range of years (`FromYear` to `ToYear`, inclusive, negative BCE), with its area, Wikipedia page, Wikidata item and, for 8,528 rows, Seshat polity ids. 377 rows are relations between polities ("(Alliance between Elam and Babylonia)"). The Middle Kingdom of Egypt has two rows, 2000–1801 and 1800–1601 BCE.
- **Year 0**: five Cliopatria rows end in year 0 (the Roman Empire's -14 to 0, then 1 to 5). No row starts in 0 or ends in -1. Cliopatria uses 0 only to end the last range before AD 1. [0051](0051-write-dates-as-signed-years-and-date-workings-from-periods-and-curated-dates.md) said Cliopatria writes years with no year 0. For these five rows, that is wrong.
- **Ore classes**: some occurrences belong to an ore class, not a source: a Pleiades copper mine doesn't say which ore was mined ([0046](0046-place-ancient-mines-and-quarries-from-pleiades.md)). A route takes from a source, so a class can't be had.

## Decision

**A profile's place is a Cliopatria entity, and its time is a range of signed years.** A profile may add `place: { cliopatria: <the entity's name, as Cliopatria writes it> }` and `years: [from, to]` (inclusive, [0051](0051-write-dates-as-signed-years-and-date-workings-from-periods-and-curated-dates.md)), always both. `period` and `region` stay, as labels for people. A profile without a place is a list, as before. Pleiades places and drawn polygons wait until a profile needs one: a point needs a distance, which is still for a later ADR.

**Cliopatria is a required dataset**, `upstream/cliopatria_polities` ([0044](0044-require-every-upstream-dataset-with-cold-backups-in-git.md)). Dagster asks GitHub for the repository's latest release and downloads the zip at its tag. The snapshot records the release, which the profile and the map show ([0036](0036-place-sources-and-profiles-in-space-and-time.md): "Profiles show which border dataset and version they use"). Its properties are kept as text, as published, and its polygons as WKB, which holds the same coordinates exactly. If the properties change, the download fails. The whole file is backed up in `snapshots/cliopatria_polities/`: 1.7 MB as Parquet with zstd (the polygons of an entity's rows repeat, and compress well). Staging reads a range ending in year 0 as ending in 1 BCE (-1), and one starting in 0 as starting in AD 1. Signed years have no year 0, and Cliopatria writes 0 only where its ranges meet AD 1.

**A profile's area is the union of its entity's polygons in every row whose years overlap the profile's.** A profile whose place names no entity with borders in its years stops the build. A misspelt name would otherwise silently leave it with nothing from the map. Areas are computed in the build with DuckDB's spatial extension, and written with the graph: `profile_areas` (the area, also as GeoJSON for the app, the rows and years it came from, and the release), `profile_occurrences` (each occurrence inside each area, and whether it was worked by the profile's last year) and `profile_sources`.

**A source's availability is decided by the profile's last year.** For each source kind with an occurrence inside the area:

| Availability | When |
|---|---|
| **yes** | an occurrence inside was worked by the profile's last year (`worked_by_year` ≤ `to`) |
| **maybe** | occurrences are inside, but none is known to have been worked by then: no year, or a later one |

A source kind with nothing inside has no row: it is not in the area.

**What a profile starts with is its list and the sources it had from the map.** A `yes` source of kind `source` joins the selection as though it were listed. A `maybe` is shown, never assumed: the user can add it ([0027](0027-count-one-step-away-as-one-raw-ingredient.md)). An ore class can be `yes` but is never added: a route takes from a source, and which ore was mined isn't recorded. The list wins: a listed source is had wherever the map puts it, and deselecting a source the map added removes it. The API's explore answer names the sources the map added (`from_map`); the CLI's explore prints each source found in the area.

**The app shows it.** The side pane shows the preset's place, its borders and release, and its sources found there, as "had" or "maybe", in words. The map draws the area and marks each place as worked by the year, present but not known to be worked by then, or outside the area. It uses fill, ring and a faint dot, with the same in words in the popup, never colour alone ([0019](0019-desktop-first-mobile-ready.md)). A year control starts at the profile's last year. Moving it recolours the map only: the profile's answers use its last year.

**The curation queue gains `date_unknown`**: each place inside a profile's area that belongs to a source the profile has only as a maybe. A cited date that it was worked by the profile's last year would turn the maybe into a yes. One item per upstream record, ranked by how many profiles it would answer for, after readers' reports and before ore candidates.

**`middle-kingdom-egypt`** names the Middle Kingdom of Egypt, 2050 to 1650 BCE.

## Consequences

- With Cliopatria v0.2.2 and the snapshots of 2026-11-22 to 27, Middle Kingdom Egypt's area comes from 2 rows (2000–1601 BCE). 35 occurrences of 7 source kinds are inside, and none is known to have been worked by 1650 BCE: every one is a maybe. Aswan's granite quarry is dated by the end of the New Kingdom (1086 BCE), Serabit el-Khadim's mines by the Archaic (550 BCE), and Tura's limestone (MRDS) not at all. The profile's answers don't change: it lists the sources it uses. The queue has 31 `date_unknown` items for it, which is where date research will change answers.
- A profile can now be written from a place and years alone, with an empty list, and still have sources: what M4c's generated profiles need.
- The area is only as good as Cliopatria's borders, which are one reading of uncertain and contested history (its README says so). The release is shown with every area.
- A place just outside an area doesn't count, however close. Distance is still for a later ADR.
- Profiles' years must overlap the entity's rows. A profile slightly wider than Cliopatria's rows (2050 against 2000 BCE) is fine; one entirely outside them stops the build.
- The build needs DuckDB's spatial extension for areas as it does for points. The app doesn't: it reads the areas as GeoJSON and which places are inside as ids.
- One fact in [0051](0051-write-dates-as-signed-years-and-date-workings-from-periods-and-curated-dates.md)'s context, that Cliopatria writes no year 0, was wrong for five rows. Its decision stands: years are signed, with no year 0. Staging reads Cliopatria's 0 as the year it stands for.

## Alternatives considered

- **Simplified polygons in a small GeoParquet**, rather than the whole file. The plan expected the whole file to be too large for git (47 MB zipped). As Parquet with zstd it is 1.7 MB, with nothing simplified, so the backup is the dataset as published.
- **Count an occurrence as had when it was worked within the profile's years**, not by their end. A place worked before the profile began was there and known. A working that is attested only later says nothing about then, which is what `maybe` means.
- **Treat a `maybe` as had**, or leave maybes out. The first overclaims ([0036](0036-place-sources-and-profiles-in-space-and-time.md)). The second hides what the user can choose to add, and what date research would change.
- **Add an ore class that is had** by adding all its minerals' sources. That claims ores no one recorded. The class is shown, so the user can add the ore's source.
- **Name the place by Wikidata item.** Items are stable, but Cliopatria gives one item to different entities (the Lower Egypt of 2200 BCE shares the Old Kingdom's item), and rows of one entity can carry different items. The name is what Cliopatria keys an entity by.
- **Let the year control change the answers.** Then a profile's answers would depend on a slider's position. The profile's years say when it is; the control only explores the map.
- **Store which occurrences are inside in `source_occurrences`.** A place can be inside many profiles' areas. A table of its own keeps occurrences one row per source kind and record.
