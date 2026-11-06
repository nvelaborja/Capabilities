# Worked examples

These come from running the reasoner over the data in `data/`. The test suite (`tests/test_reasoner.py`) checks the key numbers, so if the data changes, these results should be refreshed. To reproduce them, run the commands shown in each section.

## Q1: What would it take to make steel?

```bash
uv run capabilities need steel
```

Steel has two routes: **carburizing** (bloom iron + a carbon source + heat ≥ 900 °C for ≥ 24 h) and **crucible steel** (bloom iron + a carbon source + a crucible + heat ≥ 1200 °C for ≥ 24 h). The tree expands all the way down to ubiquitous materials. Heat is shown through the routes that can deliver it; the open fire and fire piston are flagged as too weak.

Needed by **every** route, so certain for anyone who had steel:

- **Things:** bloom iron, a bloomery furnace, charcoal, clay, timber, and standing trees to fell it from
- **Any of:** a carbon source, an iron ore, an edged tool (to fell the timber)
- **Actions:** cut timber
- **Heat:** ≥ 1100 °C for ≥ 24 h (the weakest bound shared by both routes; see "Merging effect thresholds" in `docs/data-format.md`)
- **Implied techniques:** charcoal burning, fire-making, furnace building, iron smelting, woodworking

No ancient route needs 1370 °C. Bloomery iron is never melted, and historical crucible steel was fired at about 1150–1250 °C, because carbon absorbed by the iron lowers its melting point.

**Common ancestors:** felling and cutting timber appear in the tree of everything that needs charcoal or wooden parts. The one deeper root is knapping a stone tool from ordinary fieldstone, because felling and cutting timber need an edged tool. A fire's fuel no longer needs timber, since deadwood is gathered by hand, but lighting it still does: fire drills and fire pistons are cut from timber. Only stone tools, clay furnaces, and rope (which needs cut(plant fiber)) don't depend on timber.

## Q2: Middle Kingdom Egypt — what else could they do?

```bash
uv run capabilities explore --profile middle-kingdom-egypt
```

- **Selected:** copper, tin bronze, blowpipes, copper saws, tube drills and chisels, bow drills, sledges, dolerite pounders; access to malachite, the Aswan granite outcrop, limestone, flint, and dolerite; and the actions cut, drill, and shape granite.
- **Implied:** crucibles, casting molds, rope, timber (felled from standing trees), heat ≥ 1085 °C, and the actions cut timber, reeds, and plant fiber.
- **Reachable:** granite (quarried from the outcrop by pounding), charcoal, clay and bloomery furnaces, bellows, fire drills, fire pistons, flint blades, stone choppers, wooden rollers.
- **Actions:** cut and drill everything up to granite's hardness via sand abrasive; move any load; shape granite by pounding (limestone is a *maybe*, because dolerite's toughness hasn't been sourced yet).
- **One step away:** iron is **one ingredient away**: a hematite deposit (mined with stone hammers) or limonite unlocks bloom iron, and with it steel, hardened steel, steel chisels and steel spears. Tin is one away (cassiterite).
- **Warning:** implies access to some tin ore (cassiterite); all known sources are regional, so it may have been traded.

**What-if:** `--hypothetical hematite` (iron ore) unlocks bloom iron, steel, hardened steel, steel chisels, and steel spears. No smelting know-how is needed, because the tool asks what was within reach of the ingredients.

## Q3: Feasibility checks

```bash
uv run capabilities check <job> --profile middle-kingdom-egypt
```

### One saw cut through granite (`granite-slab-saw-cut`)

A cut 2 m long and 1 m deep with an assumed kerf 0.6–1.0 cm wide removes 12,000–20,000 cm³. The job requires precision P2 (about 1 mm), with one saw and a crew of 2.

| Route | Result |
|---|---|
| Abrasive saw (copper + quartz sand) | **500–1,667 working hours** (weeks to months), from Stocks's measured 12–24 cm³/h. Verdict: **insufficient data**, because no source gives the precision of abrasive sawing yet. |
| Chiseling | Not available: copper chisels are softer than granite. |
| Diamond saw | Not available (modern); available as a hypothetical, but with no rate data. |

### Pound away one cubic metre of granite (`pound-granite-cubic-metre`)

1,000,000 cm³ at 216 cm³/h per pounder (measured at Aswan by Marčiš & Fraštia 2023), with 20 pounders at once: **about 231 working hours** (weeks). Verdict: **uncertain**, only because dolerite's fracture toughness hasn't been sourced, so the tool can't yet confirm a dolerite pounder survives pounding granite.

If the same job requires precision P2, pounding is ruled out ("reaches P0 at best; P2 is required"). Pounding roughs stone out; precise faces need a finishing step.

### Hollow out and finish a granite box (`granite-box-rough-and-finish`, illustrative)

| Step | Result |
|---|---|
| Rough out a 2 m³ interior by pounding, 4 workers | about 2,315 working hours (months) |
| Grind the inner faces flat to P2 | **insufficient data**: no measured grinding rate or precision yet |

Verdict: **insufficient data**. This is the shape of the question "could they have made this precisely in a plausible time?": the roughing time is measurable now, and the answer hinges on finishing data that still needs sourcing.
