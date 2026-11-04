# Worked examples

These are hand-checked results from running a scratch prototype reasoner over the seed slice in `data/`. They show what each of the three questions should produce, and serve as expected results for the real reasoner's tests.

## Q1: What would it take to make steel?

Steel has two routes in the slice:

- **Carburizing:** bloom iron + a carbon source + heat ≥ 900 °C for ≥ 24 h + carburizing know-how.
- **Crucible steel:** bloom iron + a carbon source + a crucible + heat ≥ 1200 °C for ≥ 24 h + crucible-steelmaking know-how.

Needed by **every** route, so certain for anyone who had steel:

- bloom iron, which needs a bloomery furnace, charcoal, any iron ore, heat ≥ 1100 °C for ≥ 2 h
- know-how: iron smelting, furnace building, charcoal burning, fire-making
- any carbon source; wood and clay (ubiquitous)

No ancient route needs 1370 °C. Bloomery iron is never melted, and historical crucible steel was fired at about 1150–1250 °C, because carbon absorbed by the iron lowers its melting point.

## Q2: Middle Kingdom Egypt — what else could they do?

Starting from `data/profiles/middle-kingdom-egypt.yaml`:

- **Implied** (every route to something in the profile needs it): crucible, casting mold, rope, dolerite (for the pounders), and the ubiquitous materials behind them.
- **Unlocked:** charcoal, clay furnace, wooden rollers, bellows, fire piston.
- **Verbs:** abrasive sawing and tube drilling work on every stone in the slice, including granite. Chiseling limestone with copper is a *maybe* (copper 2.5–3 vs limestone 3).
- **Near misses:** a bloomery furnace is one technique away (iron smelting); flint blades need flint, which is regional.
- **Warnings:** tin bronze needs tin ore, which Egypt lacked locally, so it implies trade.

**What-if:** toggling on iron smelting, smithing, carburizing, quenching, and bog iron ore unlocks bloom iron, steel, hardened steel, steel chisels, and steel spears. Hardened steel chisels (Mohs 7–8) can then cut granite (6–7) directly. Crucible steel stays a *maybe*, because the furnace's maximum (1100–1250 °C) straddles its 1200 °C requirement.

**Known over-generosity:** bellows and fire pistons unlock because no route requires knowing their design. See the design doc's open items.

## Q3: Could one saw cut through a granite block be done with copper and sand?

Job: `jobs/granite-slab-saw-cut.yaml`. One cut 2 m long and 1 m deep, with an assumed kerf 0.6–1.0 cm wide, which removes 12,000–20,000 cm³. Required precision is P2 (about 1 mm), with one saw and a crew of 2.

| Route | Available to Middle Kingdom Egypt | Time | Precision |
|---|---|---|---|
| Abrasive saw (copper + quartz sand) | yes | **500–1,667 working hours** (weeks to months), from Stocks's measured 12–24 cm³/h | insufficient data |
| Chiseling | no (copper is softer than granite) | — | — |
| Diamond saw | no (modern); yes only as a hypothetical | insufficient data | insufficient data |

At 10 working hours a day, the copper saw needs roughly 50–170 days for this one cut. The verdict is **feasible in time**; precision is **not yet known**, because no source in the slice gives the tolerance of abrasive sawing.
