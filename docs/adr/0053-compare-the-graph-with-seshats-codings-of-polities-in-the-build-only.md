# 0053. Compare the graph with Seshat's codings of polities, in the build only

- **Status:** Proposed
- **Date:** 2026-11-27

## Context

The platform plan's M4 ends with a comparison: does the graph reach what history records societies had? Profiles now have a place and years, and the sources found there ([0052](0052-give-profiles-a-cliopatria-place-and-years-and-find-their-sources-on-the-map.md)). Seshat: Global History Databank codes polities' traits, and Cliopatria gives many of its polities borders through each row's `SeshatID`.

What Seshat offered (2026-11-26 and 27):

- **The live databank** (seshat-db.com) has a public JSON API, paged, that answers without an account. Its warfare variables include military use of copper, bronze, iron and steel. Its social-complexity variables include mines or quarries. Each coding names its polity (with the polity's start and end years), a value (`present`, `absent`, `unknown`, `uncoded`), the years it covers when fewer than the polity's, a tag (`TRS` confident, `SSP` suspected, `IFR` inferred, `UND` undecided, per Seshat's code) and a description holding Seshat's references.
- **Its terms.** Public data is CC BY-SA 4.0. Downloading CSVs needs an account, and any use of the API counts as accepting the user agreement. The project's owner made an account and accepted the agreement on 2026-11-27, before anything here called the API. Only private data may not be redistributed.
- **Equinox 2020** on Zenodo is an older packaged release, and its license is stated three ways (CC BY, CC0, CC BY-NC-SA). The M4 plan chose the live API.
- **The license matters for what we derive.** CC BY-SA requires adaptations to stay CC BY-SA. This project's data is CC BY-NC-SA ([0037](0037-license-the-project-for-non-commercial-use-only.md)), which isn't compatible with it.

On 2026-11-27 the five variables have 1,820 codings of 445 polities (copper 338, bronze 363, iron 378, steel 375, mines or quarries 366). One coding names no polity. Seshat ends one polity in year 0, as Cliopatria does ([0052](0052-give-profiles-a-cliopatria-place-and-years-and-find-their-sources-on-the-map.md)).

## Decision

**Seshat's codings are a required dataset**, `upstream/seshat_codings` ([0044](0044-require-every-upstream-dataset-with-cold-backups-in-git.md)), downloaded by Dagster from the live API. Only the variables the crosswalk names are downloaded, page by page (100 a page, a second apart), with each coding kept as published. A coding whose value isn't in exactly one field named for its variable fails the download. A coding of no polity is kept with its polity empty, and staging leaves it out. The cold backup, `snapshots/seshat_codings/` (100 KB), is Seshat's data under its own license, CC BY-SA 4.0, credited as its terms ask. Staging reads year 0 as Cliopatria's is read.

**Nothing derived from Seshat enters `data/`.** The crosswalk is ours: it says which of Seshat's variables we compare, and what each means in the graph. Everything built from Seshat's codings stays in the build (`build/`): the generated profiles, what each polity had, and the comparison. None of it is written to the curated layer. If results are ever published, they go out under CC BY-SA.

**`data/crosswalks/seshat_variables.csv`** maps each variable to a comparison:

| Variable | Compares | With |
|---|---|---|
| `wf/coppers` | thing | `copper` |
| `wf/bronzes` | thing | `tin-bronze`; Seshat's bronze may be arsenical, which the graph doesn't model |
| `wf/irons` | thing | `bloom-iron`, the graph's only iron |
| `wf/steels` | thing | `steel` |
| `sc/mines-or-quarries` | worked_source | whether the map gives the area a place worked by then |

The metal variables are military use: absent means not used in war, not that the polity lacked the metal.

**Each polity Seshat codes, with Cliopatria borders, gets a generated profile.** Its id is `seshat-<polity>`, its years are the polity's, and its area is the union of Cliopatria's polity rows that carry its Seshat id and overlap those years ([0052](0052-give-profiles-a-cliopatria-place-and-years-and-find-their-sources-on-the-map.md)). Relation rows are left out. "(Kingdom of Hawaiʻi nominally subject to British Empire)" carries the Kingdom of Hawaiʻi's id, but its borders are the British Empire's. These profiles share the curated profiles' marts, marked `origin: seshat`. The app loads only curated ones, and the date queue only counts curated profiles. A generated profile has only basic inputs: the sources worked in its area by its last year. Nothing is hand-picked.

**What Seshat says a polity had** (`history_codings`): present if coded present in any of its years; else absent if coded absent; else unknown (unknown, uncoded, or no coding). Seshat's tags, whether it is disputed, and its record ids are kept beside it.

**The comparison** is a Dagster asset, `backtest`, after the graph is built, and the command `capabilities backtest`. It runs the reasoner for each generated profile and compares each variable:

| Outcome | When |
|---|---|
| `agree` | the graph reaches it and Seshat records it present, or neither |
| `history_yes_graph_no` | Seshat records it, the graph can't reach it |
| `graph_yes_history_no` | the graph reaches it, Seshat records it absent. The weaker disagreement, since Seshat's metals are military use |
| `unknown` | Seshat doesn't know, or the graph's answer is maybe |

Every "no" gives a cause: the least it takes, widening what the polity had, to reach it.

- **`ore_unrecorded`**: the sources of the ore classes with a mine worked in the area by then would do. Which ore isn't recorded, so it can't be had ([0046](0046-place-ancient-mines-and-quarries-from-pleiades.md)). It names the classes.
- **`undated`**: every place mapped in the area, worked by then or not, would do. A dated working would settle it. It names the places a date is needed for, and any worked ore-class mine needed as well (copper from one, tin from an undated place).
- **`absent`**: not even every place mapped there would. The area lacks a source, or the graph a route. It names what is still missing with every place mapped there, so what the area lacks, not what is there undated: the raw ingredients one of which would be enough (one step away, [0027](0027-count-one-step-away-as-one-raw-ingredient.md)), or else the needs every route shares that aren't met.

**Gaps** (`graph_gaps`) group what history shows and the graph can't reach. An absent gap is grouped by what is missing, since that is what to fix (its id keeps a short digest of the list). An undated or unrecorded gap is grouped by the thing alone, since the fix is the same wherever it is. The results, gaps and a summary are written beside the graph (`backtest_results.parquet`, `graph_gaps.parquet`, `backtest.json`), with the fingerprint of the build they compared. While that matches the current build, each gap is a `history_gap` item in the curation queue.

## Consequences

- With Cliopatria v0.2.2 and Seshat on 2026-11-27, 268 polities have generated profiles: 1,340 comparisons.
  - 260 agree and 408 are unknown.
  - In 667, Seshat records what the graph can't reach: 313 with the source absent, 214 undated, 140 with the ore unrecorded.
  - In 5, the graph reaches what Seshat records absent.
- The 13 gaps, by size: tin bronze where only tin is missing in 98 polities (tin-bearing gravel would do; tin is rarely in a polity's own area, which fits its having been traded), and where copper is missing too in 57; bloom iron undated in 83, copper undated in 64, steel undated in 63; copper absent in 53; and the unrecorded ores (iron 42, copper 42, steel 39, tin 17).
- Ten polities were read in full, with every disagreement naming what caused it. They were the Middle Kingdom and Saite Period of Egypt, the New Kingdom's Thutmosid period, the Achaemenid Empire, the Roman Principate, the Western Han, Classical Angkor, Anglo-Saxon England I, the Inca and the Kingdom of Hawaiʻi.
  - Reading them found the relation-row error above: before the fix, Hawaiʻi had the British Empire's mines.
- Most disagreements are the map's, not the routes'. Few places are dated before modern times, and ancient mines often don't say which ore. Date research ([0051](0051-write-dates-as-signed-years-and-date-workings-from-periods-and-curated-dates.md)) and ore attributions would move many of them to agree. The comparison measures the map as much as the graph.
- Seshat's terms can change, and they may start requiring tokens. A token would go in `pipeline/.env`, never in git. The backup keeps builds working offline meanwhile.
- The comparison is strict: a source had must be worked by the polity's last year inside its own area. Trade and distance aren't modelled, which is why bronze nearly never agrees.
- A polity's area is what Cliopatria gives its Seshat id, colonies and occupied lands included. Cliopatria puts the id on composite rows ("(Kingdom of England)", the kingdom with its colonies), and 31 of the 268 areas take such rows in. England Tudor-Stuart has iron only from a magnetite mine in New Jersey (its English mines don't say which ore), the Late Bourbon kingdom of France has Egypt's limestone quarries, and the Shuar's area gives them Ecuador's copper mines, one of the 5 cases where the graph reaches what Seshat records absent. That is Cliopatria's attribution, kept as the dataset gives it.
- "Worked by then" is any time before the polity's last year ([0052](0052-give-profiles-a-cliopatria-place-and-years-and-find-their-sources-on-the-map.md)), so mines or quarries counts workings long before the polity: Anglo-Saxon England had mines partly because Grimes Graves' flint was mined in the Neolithic.

## Alternatives considered

- **Equinox 2020 from Zenodo.** No account was needed, but its license is unclear and older. The live API's terms were accepted by the owner.
- **Keep Seshat's codings out of git and fetch them each time.** ADR 0044 requires a cold backup, and CC BY-SA permits redistributing the public data under its own license.
- **Write generated profiles to `data/profiles/`.** They would be adaptations of CC BY-SA data in a CC BY-NC-SA layer. They are also generated, not curated.
- **Count maybes as had in the comparison.** It would agree more often by assuming what isn't known ([0036](0036-place-sources-and-profiles-in-space-and-time.md)). Instead each "no" says whether the places there would have done (undated), which is the same information without the claim.
- **Let any member of a worked ore class count as had.** That claims an ore no one recorded. It is reported as the cause instead.
- **Use every Cliopatria row carrying the id**, relations included. That gave Hawaiʻi the British Empire's borders.
- **Leave out composite rows**, so a polity's area is its own territory without colonies. Some areas would shrink where the parts don't carry the id themselves, and it would set aside Cliopatria's own attribution. A later ADR can choose it if colonies' mines prove misleading.
- **Run the comparison in `capabilities build`.** It takes about ten seconds and isn't needed to answer questions. As a separate asset and command, the build stays quick, and stale results drop out of the queue.
