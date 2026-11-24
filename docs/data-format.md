# Data format and reasoning rules

The graph lives in `data/` as one YAML file per node. Each file's shape is defined by a JSON Schema in `schema/`. File names match ids (`data/things/materials/granite.yaml` has `id: granite`). Ids are unique across all things, verbs, routes, and profiles.

## The model in one paragraph

A **thing** (material, artifact, effect...) can be obtained by any one of its **routes** (OR). A route works only if **all** of its requirements are met (AND). Requirements name inputs, tools, physical **effects** ("heat of at least 1100 °C for at least 2 hours"), or **actions** ("be able to cut wood"). They often constrain a **quantity** rather than naming a specific thing: "an abrasive at least as hard as the stone being cut". **Categories** let one requirement accept many alternatives ("any carbon source"). **Know-how never blocks a route**: the tool asks what was *within reach* given the ingredients, not whether anyone actually thought of it. Routes also declare a **performance envelope** (rate, precision, capacity), which lets the tool say how long a job would take and how precise it could be.

## Layout

```
schema/                  JSON Schemas (language-neutral)
data/
  quantities/            measurable dimensions, with units and ballpark bands
  things/
    sources/             where natural resources are found (standing trees, a granite outcrop, a hematite deposit)
    materials/           natural, extracted, and produced substances (including states, e.g. hardened steel)
    artifacts/           tools, machines, and products
    techniques/          named know-how, for description (never gates anything)
    knowledge/           abstract understanding (none yet)
    effects/             physical effects with many possible sources (heat)
    categories/          is-a groupings (abrasive, fuel, chisel, plant material...), called classes in the web UI
  verbs/                 parameterized actions: cut, drill, shape, finish (target), move (load)
  routes/                ways to obtain things, produce effects, or perform verbs
  profiles/              curated starting sets (e.g. Middle Kingdom Egypt)
  crosswalks/            CSV tables matching upstream records to our ids (MRDS deposits to source kinds, things to Wikidata items, ore minerals that join the graph, rules placing Pleiades mines and quarries)
  overrides/             replacements for upstream values we believe are wrong, with the reason and references
  suppressions/          upstream records left out of the build, with why
  LICENSE                CC BY-NC-SA 4.0 (the data); the code is PolyForm Noncommercial 1.0.0
examples/jobs/           concrete tasks for feasibility checks
src/capabilities/        the Python reasoner, CLI, and local API server
tests/                   pytest suite
```

## File types

### Quantity (`data/quantities/*.yaml`)

```yaml
id: tolerance_mm          # snake_case, ending in the unit
kind: quantity
label: Precision (tolerance)
unit: mm
scale: ratio              # or ordinal (Mohs: only comparisons are meaningful)
bands:                    # optional ballpark bands; min inclusive, max exclusive
  - { id: P2, label: "Fine", min: 0.3, max: 3, typical: "good joinery" }
wikidata:                 # optional: where Wikidata holds this quantity (here on hardness_mohs)
  property: P1088
  unit: Q199              # the unit its values must be in: Q199 is "1", no unit
```

A quantity with `wikidata` is read from Wikidata for every thing in the Wikidata crosswalk, and that value is used over the curated one. A Wikidata value in another unit fails the build, rather than be read unconverted ([ADR 0043](adr/0043-take-quantities-from-wikidata-with-upstream-first-and-overrides.md); see [Where values come from](#where-values-come-from)).

Current quantities: `temperature_c`, `hardness_mohs`, `toughness_mpa_sqrt_m`, `tolerance_mm` (bands P0–P5), `duration_h` (bands minutes → geological), `mass_kg` (bands), `force_kn`, `volume_cm3`, `removal_rate_cm3_per_h`.

### Thing (`data/things/<kind>/*.yaml`)

```yaml
id: granite
kind: material            # material | artifact | technique | knowledge | effect | category | source
label: Granite
origin: extracted         # materials only: natural (gathered as is) | extracted (from a source) | produced (made)
is_a: [stone]             # categories this belongs to
quantities:
  hardness_mohs: [6, 7]   # a number or a [low, high] range
  toughness_mpa_sqrt_m: [1.1, 1.9]
```

- **Where things are found** ([ADR 0032](adr/0032-extract-materials-from-sources-by-routes.md)). A **source** says where a resource is: `availability: ubiquitous | regional`, plus `regions`. Materials taken from it are `origin: extracted`, and an ordinary route extracts them: felling standing trees needs an edged tool, quarrying the granite outcrop needs granite to be shaped by pounding, mining a hematite deposit needs a stone hammer. Materials gathered by hand as they are (deadwood, plant fiber, reed, clay, water, fieldstone, quartz sand) stay `origin: natural` with their own `availability`, since a source would add nothing.

  ```yaml
  id: granite-outcrop
  kind: source
  label: Granite outcrop
  availability: regional
  regions: ["Aswan (Egypt)", "Widespread in continental crust"]
  ```

- **Ubiquitous** sources and natural materials (standing trees, deadwood, clay, water, fieldstone, quartz sand) are assumed available everywhere. **Regional** ones must be selected, implied, or added as hypotheticals.
- **Effects** list their `dimensions` (heat: temperature, duration, volume).
- `era: modern` marks things kept only for comparison (the diamond saw).

### Verb (`data/verbs/*.yaml`)

An action that takes a parameter, so one route covers many materials: `cut(target)`, `drill(target)`, `shape(target)`, `finish(target)`, `move(load)`. `job_parameters` says how a job is sized (volume removed for cutting, mass for moving).

### Route (`data/routes/*.yaml`)

```yaml
id: cut-abrasive-saw
kind: route
label: Abrasive sawing
achieves: { verb: cut }               # exactly one of: thing | effect | verb
techniques: [abrasive-cutting]        # descriptive only
applies_to: [plant-material]          # verb routes only, optional: limit the targets
requires:                             # ALL must be met
  - { role: tool, category: saw }
  - role: consumed
    category: abrasive
    where:
      - { quantity: hardness_mohs, op: ">=", value: target.hardness_mohs }
  - { role: action, verb: cut, target: timber }
outputs: []                           # thing routes: products and byproducts (slag)
provides: {}                          # effect routes: the most the effect reaches
envelope:
  rate:
    quantity: removal_rate_cm3_per_h
    crew: 2                           # people per tool
    basis: measured
    by_target:
      - { target: granite, value: [12, 24], basis: measured }
  precision: { basis: unknown }
references:                           # at least one
  - citation: "Stocks, D. A. (2001). ..."
    doi: 10.1017/S0003598X00052777
    supports: "Sawing granite: about 12 cm³/hour..."
    status: secondary
```

**Requirement roles**

| Role | Meaning | Points at |
|---|---|---|
| `consumed` | used up | a material/artifact, or a category |
| `tool` | used, not used up | a material/artifact, or a category |
| `effect` | a physical effect | an effect, usually with `where` conditions |
| `action` | the ability to do something | a verb and a target, e.g. `cut` + `timber` |

**Conditions** (`where`) compare a quantity with a number (`value: 1100`), a band (`band: hours`, meaning the band's lower edge), or the verb's target (`value: target.hardness_mohs`).

**Envelopes** have `rate` (by target, per tool, with `crew` people per tool), `precision` (bands, `[finest, roughest]`), and `capacity` (per unit with a scaling rule). Each entry has a `basis`: `measured`, `derived`, `estimated`, or `unknown`. Unknown is allowed and honest; the tool reports "insufficient data" instead of guessing.

### Profile (`data/profiles/*.yaml`)

A curated set of things a group is known to have made (`{ id: copper-saw }`) or done (`{ verb: cut, target: granite }`), including natural resources they had access to. Each item can carry its own references.

### Crosswalk (`data/crosswalks/*.csv`)

A hand-kept table that matches records in an upstream dataset to our ids ([ADR 0034](adr/0034-build-the-graph-from-upstream-datasets-and-a-curated-layer.md)). It is CSV rather than YAML because it is a table, and the build loads it as written. There are three:

`mrds_sources.csv` matches USGS MRDS deposits to source kinds, which places each source on the map ([ADR 0041](adr/0041-place-sources-with-mrds-deposits-through-a-crosswalk.md)):

| Column | Meaning |
|---|---|
| `source_id` | A thing with `kind: source` |
| `field` | `ore` (the deposit's ore minerals) or `commodity` (its commodities) |
| `value` | The MRDS name to match, as a whole list item, ignoring case (`Hematite`, `Limestone`) |
| `deposit_type` | Optional: the deposit's type must also contain this (`placer` for tin gravel) |
| `notes` | Why the match holds |

```csv
source_id,field,value,deposit_type,notes
tin-gravel,ore,Cassiterite,placer,"Placers only: tin gravel is stream-sorted cassiterite, not a vein."
```

A deposit matching a row is an occurrence of that source kind, and one deposit can be an occurrence of several. Leave a source kind out when no rule fits it well: an unmapped source is curation work, but a wrong match puts false places on the map. The build fails if a row names something that isn't a source, or repeats another row.

`wikidata_things.csv` matches things to Wikidata items, whose quantities the graph then uses ([ADR 0043](adr/0043-take-quantities-from-wikidata-with-upstream-first-and-overrides.md)):

| Column | Meaning |
|---|---|
| `id` | One of our things, at most once |
| `wikidata` | A Wikidata item (`Q41177`), at most once |
| `notes` | Why it is the same thing, usually the item's own description |

```csv
id,wikidata,notes
granite,Q41177,"Wikidata ""granite"": intrusive, felsic, igneous rock."
```

Match only when the item is the same thing. Our copper and tin are the metals, and Wikidata gives the metals' properties on the elements, so they match the elements. Quartz sand has no item of its own, and the quartz item isn't sand, so it stays unmatched.

After adding or changing a row, query Wikidata again (`cd pipeline && uv run dg launch --assets 'upstream/wikidata_quantities'`, then `uv run capabilities backup` and commit): the snapshot holds only the items that were crosswalked when it was taken, and until then the thing keeps its curated value, if it has one.

Don't keep a curated value that Wikidata gives: remove it, and the references that backed only it. The upstream value is the one used, every build has it ([ADR 0044](adr/0044-require-every-upstream-dataset-with-cold-backups-in-git.md)), and a copy in the curated layer would only go stale.

`ore_minerals.csv` brings ore minerals into the graph from upstream ([ADR 0045](adr/0045-bring-ore-minerals-in-from-upstream-roast-sulphides-and-queue-the-gaps.md)). Each row becomes three nodes: the mineral (a material in its ore class, named and described from Wikidata, with its quantities from Wikidata), its deposit (a source whose places are the MRDS deposits listing it as an ore) and a mining route copied from a curated one.

| Column | Meaning |
|---|---|
| `id` | Our id for the mineral; its nodes are `<id>`, `<id>-deposit` and `mine-<id>`. None may clash with a curated id. Empty for a rejected row. |
| `wikidata` | Its Wikidata item |
| `mrds_ore` | Its name in MRDS's ore field (`Chalcopyrite`), which places its deposits |
| `class` | The ore class it joins: `copper-ore`, `copper-sulphide-ore` (roasted before smelting), `iron-ore`, `tin-ore`; or `none` for a mineral reviewed and rejected |
| `mined_like` | The curated route it is mined like (`mine-malachite`, `mine-hematite`); empty for a rejected row |
| `citation`, `url`, `supports` | The reference that puts it in its class (or rejects it), and what it supports. Credited in CREDITS.md |
| `notes` | Added to its description |

```csv
id,wikidata,mrds_ore,class,mined_like,citation,url,supports,notes
siderite,Q192669,Siderite,iron-ore,mine-hematite,"Föll, H. ...",https://...,"Siderite is relatively easy to smelt...",An iron carbonate.
```

Add a mineral only with a reference that it was smelted as its class says; leave it in the curation queue otherwise (`uv run capabilities queue`). Rejecting a mineral (`none`, with the reference that says why) takes it off the queue. After adding rows, query Wikidata again, as for `wikidata_things.csv`.

`pleiades_sources.csv` places Pleiades' ancient mines and quarries at our sources and ore classes, with the years they are attested ([ADR 0046](adr/0046-place-ancient-mines-and-quarries-from-pleiades.md)). One row per rule:

| Column | Meaning |
|---|---|
| `target` | A source (`granite-outcrop`), or an ore class (`copper-ore`) when the place doesn't say which ore was mined |
| `places` | `mine` or `quarry`. Pleiades' deprecated "mine, quarry" type counts as both |
| `word` | What the place must name: one of its tags, or a whole word in its title or description ("Iron Age" doesn't count as iron) |
| `notes` | Why the rule is right |

```csv
target,places,word,notes
copper-ore,mine,copper,"A copper mine: which ore isn't recorded, so the place belongs to the class."
```

Matching needn't be perfect: where a material was found matters least to the app's questions. Suppress a wrong match (dataset `pleiades`); unmatched mines and quarries are the last kind in the curation queue.

### Override (`data/overrides/*.yaml`)

Replaces an upstream value we believe is wrong. Upstream sources are never edited; the build applies the override and the app shows it beside the value it replaces ([ADR 0043](adr/0043-take-quantities-from-wikidata-with-upstream-first-and-overrides.md)).

```yaml
id: <thing>-hardness
kind: override
thing: <thing>
quantity: hardness_mohs
value: [6, 7]                                # ours
replaces: { dataset: wikidata, value: [5, 7] }   # upstream's, when the override was written
reason: Why upstream's value is wrong, in a sentence.
references:                                  # at least one
  - { citation: "...", supports: "...", status: unverified }
```

There are none yet. The thing must be in the Wikidata crosswalk and the quantity read from Wikidata: a value only the curated layer gives is corrected in the thing's own file. If upstream changes, the build marks the override stale for review. A value can be overridden once.

### Suppression (`data/suppressions/suppressed_records.csv`)

Upstream records left out of the build: a duplicate, bad coordinates, the wrong mineral. Not for unwelcome history: a deposit found in modern times stays, with its dates ([ADR 0034](adr/0034-build-the-graph-from-upstream-datasets-and-a-curated-layer.md)).

| Column | Meaning |
|---|---|
| `dataset` | `mrds` (a deposit, by `dep_id`), `wikidata` (an item, by Q id) or `pleiades` (a place, by its id) |
| `record_id` | The record |
| `reason` | Why it doesn't belong |

### Where values come from

A thing's quantity value comes from, in order:

1. an **override**, if there is one;
2. the **upstream** value, when the thing is in the Wikidata crosswalk and Wikidata has one (best-ranked statements; a statement with bounds is a range);
3. the **curated** value in the thing's file.

A curated value that disagrees with upstream isn't lost: the app shows it beside the upstream value, and the build marks the disagreement. The built graph's `graph_facts.parquet` records, for every value, which layer it came from ([data pipeline](architecture/data-pipeline.md)).

### Job (`examples/jobs/*.yaml`)

A concrete task for a feasibility check: a verb, a target, its size, and limits. Multi-step jobs list `steps`, each with its own verb, target, and size.

```yaml
limits:
  precision: P2          # required on the final step
  max_duration_h: 2000   # total working-time budget
  max_crew: 20           # people available at once
  max_units: 20          # tools that can work at once (e.g. workers that fit around a trench)
```

## Reasoning rules

The reasoner in `src/capabilities/reasoner.py` follows these rules.

### Selected, implied, reachable

- **Selected:** what the user says was made or done (from a profile, plus or minus their own choices).
- **Hypothetical:** what-if additions. They are treated like selections but reported separately.
- **Implied:** what every route to a selected item needs, recursively. For example, anyone who had tin bronze had copper, a crucible, and heat of at least 1085 °C. Having something also implies the capability of making it: the techniques shared by all its routes are listed as implied.
- **Reachable:** everything that can be made or extracted from selected + implied + ubiquitous sources and materials, repeating until nothing new appears. Cycles (heat needs charcoal, charcoal needs a fire) are fine.
- **One step away (near misses):** things that adding one raw ingredient would make reachable, however long the chain from it. A raw ingredient is something no route makes: a source (a hematite deposit), a natural material, or a thing with no known route. Adding a made thing directly doesn't count ([ADR 0027](adr/0027-count-one-step-away-as-one-raw-ingredient.md)).

### Core rules

1. **Know-how never gates.** If the ingredients are there, the route counts as within reach. Techniques are labels for describing routes and for reporting what having something implies.
2. **Ubiquitous sources and natural materials are free.** Regional ones must be selected, implied, or hypothetical. Extracted materials come from their source by a route, like anything else. Implied regional needs (tin ore for bronze, in Egypt) produce a trade warning.
3. **Ranges give three answers.** Comparing ranges yields *yes* (true for every value), *no* (true for none), or *maybe* (overlap). Copper chisels (2.5–3) on limestone (3) are a *maybe*.
4. **`provides` is a maximum.** An effect route's `provides` values are the most it can deliver; a range means that maximum is uncertain. A furnace that reaches 1100–1250 °C satisfies "≥ 1100" (yes) and "≥ 1200" (maybe).
5. **Missing data is "maybe", never "no".**
6. **Implied effect levels count.** If a group made something that needed at least 1100 °C, they reached 1100 °C, even if no heat route in the graph explains how. That level can satisfy other requirements at or below it.

### Merging effect thresholds

When every route to something needs the same effect at different levels, backward inference keeps the **weakest bound shared by every route**, quantity by quantity. Steel's carburizing route needs heat ≥ 900 °C for 24 h and its crucible route ≥ 1200 °C for 24 h; both also need bloom iron (≥ 1100 °C for 2 h). Within a route the strongest bound applies, so the routes need ≥ 1100 °C/24 h and ≥ 1200 °C/24 h, and the certain need for steel is **≥ 1100 °C for ≥ 24 h**.

This is sound (each route's own bound implies the merged one), but it has side effects we may want to revisit:

- **It understates.** The merged bound is weaker than any single route's, so it can say less than the truth (a group with steel certainly reached 1100 °C, though every real route needed more).
- **It mixes quantities across routes.** Temperature may come from one route's minimum and duration from another's, so the merged pair might not match any single route.
- **It drops quantities.** If one route constrains duration and another does not, duration is dropped entirely.
- **It only applies to effects.** Things, categories, and actions are intersected exactly, so "charcoal" in one route and "any carbon source" in another do not merge into "any carbon source".
- **It feeds forward.** Implied effect levels (rule 6) are used as achieved capabilities, so any understatement carries into what is reachable.

### Tech levels

Tech levels order items for display, highest first ([ADR 0018](adr/0018-rank-dependencies-by-tech-level.md)). They never decide whether something is shown.

- Sources and natural materials are level 0.
- A route is at the highest level among its requirements.
- A thing is one above its easiest route.
- A category takes its lowest member. A heat requirement takes the easiest heat source that can reach its threshold, so "≥ 1200 °C" ranks above "≥ 900 °C".
- Ties go to the item that certainly needs more, then alphabetical.

For example: deadwood 0, stone chopper 1, timber and cut timber 2, heat 4, charcoal 5, bloom iron 7, steel 8, hardened steel 9. The code is in `src/capabilities/levels.py`.

### Feasibility checks (question 3)

- Each step is checked against every route that performs its verb on its target.
- **Time** = volume ÷ (rate × tools working at once). Tools at once = `max_units`, limited by `max_crew ÷ crew per tool`.
- **Precision** compares the route's bands with the required band.
- **Verdicts:** feasible, uncertain, insufficient data, "no known route meets these constraints", or not available. Never "impossible".
- **The generous end decides infeasibility.** A route is ruled out on time only if even its *fastest* estimate is over budget.
- Multi-step jobs add up durations; precision is checked on the final step.

## Evidence conventions

- Every route needs at least one reference. Things should have them when they carry numbers.
- `status` is honest about checking: `unverified` (cited, not checked), `secondary` (taken from a summary of the source), `verified` (someone read the source and confirmed the claim).
- `TODO-source` in a note marks a number or claim that still needs a source. Search for it to find work to do.
- `supports` says exactly which claim the source backs.
