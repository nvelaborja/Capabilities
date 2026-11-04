# Data format

The graph lives in `data/` as one YAML file per node. Each file's shape is defined by a JSON Schema in `schema/`. File names match ids (`data/things/materials/granite.yaml` has `id: granite`). Ids are unique across all things, verbs, routes, and profiles.

## The model in one paragraph

A **thing** (material, artifact, technique, effect...) can be obtained by any one of its **routes** (OR). A route works only if **all** of its requirements are met (AND). Requirements often constrain a **quantity** rather than naming a specific thing: "heat of at least 1100 °C for at least 2 hours", or "an abrasive at least as hard as the stone being cut". **Categories** let one requirement accept many alternatives ("any carbon source"). Routes also declare a **performance envelope** (rate, precision, capacity), which lets the tool say not just *whether* something was possible, but how long it would take and how precise it could be.

## Layout

```
schema/                  JSON Schemas (language-neutral)
data/
  quantities/            measurable dimensions, with units and ballpark bands
  things/
    materials/           natural and produced substances (including states, e.g. hardened steel)
    artifacts/           tools, machines, and products
    techniques/          practical know-how
    knowledge/           abstract understanding (none yet)
    effects/             physical effects with many possible sources (heat)
    categories/          is-a groupings (abrasive, fuel, chisel...)
  verbs/                 parameterized capabilities: cut(target), drill(target), shape(target), move(load)
  routes/                ways to obtain things, produce effects, or perform verbs
  profiles/              curated starting sets (e.g. Middle Kingdom Egypt)
examples/jobs/           concrete tasks for feasibility checks
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

Current quantities: `temperature_c`, `hardness_mohs`, `tolerance_mm` (bands P0–P5), `duration_h` (bands minutes → geological), `mass_kg` (bands), `force_kn`, `volume_cm3`, `removal_rate_cm3_per_h`.

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
```

- **Ubiquitous** natural materials (wood, clay, water, fieldstone) are assumed available everywhere. **Regional** ones must be in the starting set; the tool only warns about them.
- **Effects** list their `dimensions` (heat: temperature, duration, volume).
- `era: modern` marks things kept only for comparison (the diamond saw).

### Verb (`data/verbs/*.yaml`)

A capability that takes a parameter, so one route covers many materials. `job_parameters` says how a job is sized (volume removed for `cut`, mass for `move`).

### Route (`data/routes/*.yaml`)

```yaml
id: cut-abrasive-saw
kind: route
label: Abrasive sawing
achieves: { verb: cut }               # exactly one of: thing | effect | verb
requires:                             # ALL must be met
  - { role: tool, category: saw }
  - role: consumed
    category: abrasive
    where:
      - { quantity: hardness_mohs, op: ">=", value: target.hardness_mohs }
  - { role: know_how, thing: abrasive-cutting }
outputs: []                           # thing routes: products and byproducts (slag)
provides: {}                          # effect routes: what the effect reaches
envelope:
  rate:
    quantity: removal_rate_cm3_per_h
    crew: 2
    basis: measured
    by_target:
      - { target: granite, value: [12, 24], basis: measured }
  precision: { basis: unknown }
references:                           # at least one
  - citation: "Stocks, D. A. (2001). ..."
    supports: "Sawing granite: about 12 cm³/hour..."
    status: secondary
```

**Requirement roles**

| Role | Meaning | Points at |
|---|---|---|
| `consumed` | used up | a thing or category |
| `tool` | used, not used up | a thing or category |
| `know_how` | must already be known | a technique or knowledge item |
| `effect` | a physical effect | an effect, usually with `where` conditions |

**Conditions** (`where`) compare a quantity with a number (`value: 1100`), a band (`band: hours`, meaning the band's lower edge), or the verb's target (`value: target.hardness_mohs`).

**Envelopes** have `rate` (by target), `precision` (bands), and `capacity` (per unit with a scaling rule). Each entry has a `basis`: `measured`, `derived`, `estimated`, or `unknown`. Unknown is allowed and honest; the tool reports "insufficient data" instead of guessing.

### Profile (`data/profiles/*.yaml`)

A curated starting set, e.g. Middle Kingdom Egypt. Each item can carry its own references. Users start from a profile and toggle items on or off; toggled-on items are hypothetical.

### Job (`examples/jobs/*.yaml`)

A concrete task for a feasibility check: a verb, a target, its size, and limits (precision band, maximum duration, maximum crew).

## Reasoning rules

These are the rules the reasoner must follow. The scratch prototype used to test this slice follows them.

1. **Know-how is never derived.** Techniques and knowledge come only from the starting set, from toggles, or from backward inference (if every route to something they had needs a technique, they had it).
2. **Ubiquitous natural materials are free.** Everything else must be produced or in the starting set.
3. **Repeat until nothing changes.** Cycles (iron tools make better iron) are fine.
4. **Ranges give three answers.** Comparing ranges yields *yes* (true for every value), *no* (true for none), or *maybe* (overlap). Copper chisels (2.5–3) on limestone (3) are a *maybe*.
5. **`provides` is a maximum.** An effect route's `provides` values are the most it can deliver; a range means that maximum is uncertain. A furnace that reaches 1100–1250 °C satisfies "≥ 1100" (yes) and "≥ 1200" (maybe).
6. **Missing data is "maybe", never "no".** A condition on a quantity nobody has filled in is a *maybe*.
7. **Infeasibility uses the generous end.** When reporting that a route cannot meet a job's limits, use the most favorable end of every range, and say "no known route meets these constraints", never "impossible".

## Evidence conventions

- Every route needs at least one reference. Things should have them when they carry numbers.
- `status` is honest about checking: `unverified` (cited, not checked), `secondary` (taken from a summary of the source), `verified` (someone read the source and confirmed the claim).
- `TODO-source` in a note marks a number or claim that still needs a source. Search for it to find work to do.
- `supports` says exactly which claim the source backs.
