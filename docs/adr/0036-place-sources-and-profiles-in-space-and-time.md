# 0036. Place sources and profiles in space and time

- **Status:** Proposed
- **Date:** 2026-11-20
- **Supersedes (when accepted):** [0012](0012-use-regionality-only-for-warnings.md). Amends [0003](0003-model-timeless-kinds-of-things.md): the graph of kinds and routes stays timeless, but where sources are and when they were known becomes data.

## Context

Sources ([0032](0032-extract-materials-from-sources-by-routes.md)) say where a resource is found as free text ("Aswan", "Sinai"), and profiles are hand-picked lists. [0012](0012-use-regionality-only-for-warnings.md) kept geography out because modelling it was a large project. Upstream datasets now make it practical:

- MRDS gives thousands of deposits with coordinates.
- Pleiades gives ancient places, with the periods they are attested in.
- Seshat's Cliopatria dataset gives polity borders over time.

A deposit can also be physically present without anyone known to have worked it. A mine opened in 1900 still says something about 1500 BCE: the ore was there, and someone *could* have found a surface vein, even if we know of no one who did. That is the kind of "could they have?" the tool exists to answer.

## Decision

We will give sources and profiles a place and a time.

- **Sources stay kinds in the graph** ("hematite deposit"), so routes and reasoning don't change. Each source kind gets **occurrences** in a separate geospatial layer, not drawn as graph nodes. An occurrence has:
  - a geometry (a point or polygon);
  - its upstream record (MRDS, Pleiades, Mindat if licensed) or curated provenance ([0034](0034-build-the-graph-from-upstream-datasets-and-a-curated-layer.md));
  - optionally, a **first known working** date range, with its basis and references;
  - a **state**: worked (with dates), known but not worked, or suppressed, with a reason.
- **Profiles get a place and a time.** The place is a polygon, a Pleiades place or a Cliopatria polity. The time is a date range. Hand-picked selections still work and still override.
- **Availability of a source for a profile is computed spatially**, and answers in three values ([0007](0007-compare-ranges-with-three-answers.md)):

  | Availability | When | Meaning |
  |---|---|---|
  | **yes** | An occurrence inside the profile's area was worked by its date | Available |
  | **maybe** | An occurrence was there, with no known working by then | Shown as "present, not known to be worked by then", and never assumed: the user can add it, as with one step away ([0027](0027-count-one-step-away-as-one-raw-ingredient.md)) |
  | **not in the area** | Nothing inside the area | As today: the source must be added, and an implied one gives the trade warning |

  Distance, so that "nearby" counts, comes in a later ADR.
- **Dates are signed integer years, as ranges, with a basis.** A single date is a range of one year. We pick one numbering convention for BCE years and say so in the data format.
- **Time does not enter routes.** Routes say what it physically takes, and stay timeless ([0003](0003-model-timeless-kinds-of-things.md)). Time only affects which sources a profile has.

**Storage and tools:**

- Geometries are stored as GeoParquet or Iceberg geometry columns, and queried with DuckDB's spatial extension, plus Apache Sedona on Spark if needed. Which engine dbt uses follows the engine ADR from [0033](0033-build-a-python-data-platform-around-the-graph.md).
- The web app gains a map view (MapLibre GL, BSD licensed) for profiles and occurrences.
- Pleiades and MRDS are usable as far as we know. Cliopatria's and Mindat's licenses must be checked before ingesting ([0014](0014-license-code-gpl-and-data-cc-by.md)).

## Consequences

- Profiles can be generated: any polity and date in Cliopatria or Seshat becomes a starting point, and the comparison with history in the plan becomes possible.
- "Present, not known to be worked" adds a new, useful kind of answer, and more "maybe" results. The interface must explain them clearly.
- Most deposits in MRDS are modern and American, and few have working dates. Without curated or agent-researched dates ([0035](0035-propose-curated-facts-with-audited-agents.md)), most occurrences will be "known but not worked", so the curation queue gains date research.
- Borders of past polities are uncertain and contested. Profiles show which border dataset and version they use.
- The reasoner stays the same, but its inputs gain a spatial step before it runs.

## Alternatives considered

- **Keep regions as free text** ([0012](0012-use-regionality-only-for-warnings.md)). No spatial work, but profiles can't be generated, and "present but not known" can't be expressed.
- **Draw each occurrence as a graph node.** Thousands of nodes for one kind of deposit. Kinds belong in the graph, and places on a map.
- **Drop occurrences with no known working date, or only modern ones.** Simpler answers, but it throws away the "could have found it" case the user wants to see.
- **Treat "present" as "available".** Overclaims: being near an ore body is not the same as knowing it was there.
- **Put dates on routes ("bloomery smelting from 1200 BCE").** That is attestation of techniques, not physics. It stays out ([0003](0003-model-timeless-kinds-of-things.md)).
