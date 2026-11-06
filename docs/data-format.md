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
    materials/           natural and produced substances (including states, e.g. hardened steel)
    artifacts/           tools, machines, and products
    techniques/          named know-how, for description (never gates anything)
    knowledge/           abstract understanding (none yet)
    effects/             physical effects with many possible sources (heat)
    categories/          is-a groupings (abrasive, fuel, chisel, plant material...), called classes in the web UI
  verbs/                 parameterized actions: cut, drill, shape, finish (target), move (load)
  routes/                ways to obtain things, produce effects, or perform verbs
  profiles/              curated starting sets (e.g. Middle Kingdom Egypt)
  LICENSE                CC BY 4.0 (the data); the code is GPL-3.0
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
```

Current quantities: `temperature_c`, `hardness_mohs`, `toughness_mpa_sqrt_m`, `tolerance_mm` (bands P0–P5), `duration_h` (bands minutes → geological), `mass_kg` (bands), `force_kn`, `volume_cm3`, `removal_rate_cm3_per_h`.

### Thing (`data/things/<kind>/*.yaml`)

```yaml
id: granite
kind: material            # material | artifact | technique | knowledge | effect | category
label: Granite
origin: natural           # materials only: natural | produced
availability: regional    # natural materials only: ubiquitous | regional
regions: ["Aswan (Egypt)"]
is_a: [stone]             # categories this belongs to
quantities:
  hardness_mohs: [6, 7]   # a number or a [low, high] range
  toughness_mpa_sqrt_m: [1.1, 1.9]
```

- **Ubiquitous** natural materials (wood, clay, water, fieldstone, quartz sand) are assumed available everywhere. **Regional** ones must be selected, implied, or added as hypotheticals.
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
  - { role: action, verb: cut, target: wood }
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
| `action` | the ability to do something | a verb and a target, e.g. `cut` + `wood` |

**Conditions** (`where`) compare a quantity with a number (`value: 1100`), a band (`band: hours`, meaning the band's lower edge), or the verb's target (`value: target.hardness_mohs`).

**Envelopes** have `rate` (by target, per tool, with `crew` people per tool), `precision` (bands, `[finest, roughest]`), and `capacity` (per unit with a scaling rule). Each entry has a `basis`: `measured`, `derived`, `estimated`, or `unknown`. Unknown is allowed and honest; the tool reports "insufficient data" instead of guessing.

### Profile (`data/profiles/*.yaml`)

A curated set of things a group is known to have made (`{ id: copper-saw }`) or done (`{ verb: cut, target: granite }`), including natural resources they had access to. Each item can carry its own references.

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
- **Reachable:** everything that can be made from selected + implied + ubiquitous materials, repeating until nothing new appears. Cycles (heat needs charcoal, charcoal needs a fire) are fine.
- **One step away (near misses):** things that adding one raw ingredient would make reachable, however long the chain from it. A raw ingredient is something no route makes: a natural material, or a thing with no known route. Adding a made thing directly doesn't count ([ADR 0027](adr/0027-count-one-step-away-as-one-raw-ingredient.md)).

### Core rules

1. **Know-how never gates.** If the ingredients are there, the route counts as within reach. Techniques are labels for describing routes and for reporting what having something implies.
2. **Ubiquitous natural materials are free.** Regional ones must be selected, implied, or hypothetical. Implied regional needs (tin ore for bronze, in Egypt) produce a trade warning.
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

- Natural materials are level 0.
- A route is at the highest level among its requirements.
- A thing is one above its easiest route.
- A category takes its lowest member. A heat requirement takes the easiest heat source that can reach its threshold, so "≥ 1200 °C" ranks above "≥ 900 °C".
- Ties go to the item that certainly needs more, then alphabetical.

For example: wood 0, stone chopper 1, cut wood 2, heat 4, charcoal 5, bloom iron 7, steel 8, hardened steel 9. The code is in `src/capabilities/levels.py`.

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
