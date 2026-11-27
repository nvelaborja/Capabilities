# 0051. Write dates as signed years, and date workings from Pleiades' periods and curated dates

- **Status:** Proposed
- **Date:** 2026-11-26

## Context

Profiles are to get a place and a time, and a source's availability for a profile will depend on whether its occurrences were worked by the profile's date ([0036](0036-place-sources-and-profiles-in-space-and-time.md)). That needs the year each occurrence is known to have been worked by, written one way.

What the occurrences had (2026-11-26):

- **MRDS** gives a first production year for some deposits: 6,975 of 39,120 occurrences, all CE (968 to 2006). The rest are `present`, with no known working date ([0041](0041-place-sources-with-mrds-deposits-through-a-crosswalk.md)).
- **Pleiades** mines and quarries are `worked` because they are attested, with the years they are attested from and to and their named periods, but no `worked_by_year` ([0046](0046-place-ancient-mines-and-quarries-from-pleiades.md)). That ADR said the year was the end of the earliest attested period, which needs Pleiades' period vocabulary, another dataset.
- **Nothing curated** could date an occurrence: no fact in `data/` names an upstream record.

The datasets M4 brings in write years the same way: Cliopatria's `FromYear` and `ToYear` and Pleiades' periods are signed, negative BCE, with no year 0. Pleiades publishes its periods as Turtle (`time-periods.ttl`, 95 KB, CC BY 3.0): 220 periods, each with a label and, in its scope note, its years as `[[from, to]]`. 63 notes give no years: the centuries ("fifth century before the common era"), and some regional periods whose years are only in the label ("Early Cycladic (3100-2000 BCE)"). Of the 42 periods Pleiades' mines and quarries name, 9 are undated.

## Decision

**A year is a signed integer: negative is BCE, positive CE, and there is no year 0** (1 BCE is followed by 1 CE). That is how Cliopatria and Pleiades write them, so neither is converted. A range is `[from, to]`, inclusive. The schema's shared `year` rejects 0. The app writes years as historians do: 550 BC, AD 300, and plain from 1000 on (1860).

**Pleiades' periods are a required dataset**, `upstream/pleiades_periods` ([0044](0044-require-every-upstream-dataset-with-cold-backups-in-git.md)): Dagster downloads the Turtle and reads each period's key (what a place's `timePeriodsKeys` names), label, scope note, and the years the note gives. A note with no years leaves them empty, and the snapshot lists those periods: their years aren't worked out from the label or the name, which would be our reading, not Pleiades' data. If the Turtle's format changes so that a period can't be read, the download fails rather than drop it. Cold backup in `snapshots/pleiades_periods/` (11 KB).

**A Pleiades place was worked by the end of its earliest-ending dated period**: it is attested, and so worked ([0046](0046-place-ancient-mines-and-quarries-from-pleiades.md)), within that period, so by its end. Undated periods are passed over. A period that hasn't ended (Modern, to 2100) ends in the year the places snapshot was taken. A place with no dated period keeps no year and stays `worked`, as before.

**A curated working date wins over the dataset's.** A `date` document in `data/dates/` names an upstream record (`occurrence: { dataset, record }`), the year it is known to have been worked by (`worked_by`), a reason, and at least one reference, checked like any other ([0047](0047-check-citations-against-openalex-and-crossref.md)). The build uses it instead of the dataset's year, keeps the dataset's beside it, and marks the occurrence `worked`. A record has one date (validate and the build both check). A date that names no occurrence, from a typo or a record the dataset has since dropped, warns in the build rather than stops it. Dates aren't nodes: like overrides ([0043](0043-take-quantities-from-wikidata-with-upstream-first-and-overrides.md)), they are applied in the build, to `source_occurrences`.

**Every occurrence says where its year came from**: `worked_by_basis` is `first production` (MRDS), `period` (Pleiades, with the period's label in `worked_by_note`) or `curated` (with the date's id, reason, references, and `upstream_worked_by_year`). The map's popup says it in words: "Known to have been worked by 550 BC. Attested in Archaic (Greco-Roman; 750-550 BCE/BC), which had ended by then."

## Consequences

- With the snapshots of 2026-11-24 (places) and 2026-11-27 (periods), 416 of 421 Pleiades occurrences get a year: 187 BCE, 228 from AD 1 to 1000, and 1 modern. The Roman period (ends AD 300) dates 224 of them, then the Archaic (65), Classical (58) and Hellenistic (56). 4 places keep none (attested only in undated periods, or in none).
- Many years are later than the working began. Aswan's quarries are dated by the end of the New Kingdom (1086 BC), though granite was quarried there long before: Pleiades attests the place from the New Kingdom on. A curated date with a reference corrects one such case, and the queue will show where that matters (M4b). The year is a "by then", never "began then".
- Pleiades' periods are broad, and regional periods cut by Pleiades' own conventions. That precision is enough for comparing with a profile's centuries; it would not be for decades.
- There are no curated dates yet: one needs a work that dates a named place, and none is invented.
- `data/dates/` is a new kind of curated file, with its schema (`schema/date.schema.json`), and the reference checks, credits and validate read it like the others.

## Alternatives considered

- **Astronomical years** (0 = 1 BCE, −1 = 2 BCE). Arithmetic across the era boundary is simpler, but every import would need shifting by one and every display shifting back, and a missed shift is an error of a year that no test would notice. Nothing compares dates finely enough to need it.
- **Read undated periods' years from their labels or names** ("Early Cycladic (3100-2000 BCE)", "fifth century BCE"). It would date the 4 places left, but labels are written for people, not parsing, and a century's bounds are our convention. If it matters, Pleiades can be asked to add the years, or a curated date can be written.
- **Pleiades' `minDate`** (the start of a place's attestation). It is earlier, but a place attested from a period's start wasn't necessarily worked at its start; the end of the period is what the attestation supports.
- **The latest end of the place's periods**, or the end of its first-starting period. The latest is too late to be useful; the end of the first-starting period can be later than another's end when periods overlap, and the earliest end is the strongest claim the attestations support.
- **Curated dates as a CSV in `data/crosswalks/`**, as the plan first had it. A crosswalk matches records to our ids; a date is a fact with references, like an override. As YAML documents, the reference checks, credits and validate read them without new code for each, and a date can cite several works.
- **The GIS package of `pleiades.datasets`**, which carries each period's years in a CSV. It is updated less often than the vocabulary, and would add a second Pleiades download for the same years.
