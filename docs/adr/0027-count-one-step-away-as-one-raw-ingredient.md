# 0027. Count "one step away" as one raw ingredient, however deep

- **Status:** Accepted
- **Date:** 2026-11-06
- **Supersedes:** the definition of near misses ("one requirement away") in [0006](0006-separate-selected-implied-and-reachable.md)

## Context

Near misses ("one step away") were things with a route missing exactly one **direct** requirement. That said nothing about how far away the missing requirement itself was. With only a copper chisel selected, hardened steel was one step away because its route lacks only steel, even though steel lacks bloom iron and bloom iron lacks iron ore. The answer happened to be right, since one ore unlocks the whole chain. But if iron ore had needed two unselected things, hardened steel would still have been called one step away.

## Decision

We will call a thing **one step away** when adding a single **raw ingredient** to the selection makes it reachable (yes or maybe), however long the chain from that ingredient to the thing.

- A raw ingredient is a material or artifact that no route makes: a natural material such as hematite, or a thing with no known route such as the modern diamond saw. These are the only things that can be gained without first having something else.
- Adding a made thing directly doesn't count, since that would hide everything still missing beneath it.
- For each raw ingredient not already reachable, the reasoner reruns the forward closure with that ingredient added and records every newly reachable thing, the routes that now work, and the ingredient. The same rules apply as everywhere else: thresholds, categories, implied effect levels and "maybe".
- The lists show what to add: "Hardened steel, add hematite or limonite".

## Consequences

- "One step away" now means what it says. A thing two raw ingredients away is out of reach, not one step away.
- Things whose gap is not an ingredient at all, such as heat hotter than any known furnace, are no longer one step away. No single addition fixes them.
- It costs one closure per raw ingredient: 12 today, a few milliseconds. If the graph grows to hundreds of raw ingredients, we may need to share work between closures or cache results per selection.
- The near-miss record changes shape slightly: `missing` is now the raw ingredient's id, not a requirement label, and a thing can appear once per ingredient and route.

## Alternatives considered

- **Keep "one direct requirement missing".** Cheap, but wrong for deep chains, which is the case the user raised.
- **Count missing leaves with a cost function** (each missing raw ingredient costs 1, a route costs the sum of its gaps). This handles distances above 1, but sums double-count shared ingredients, and it would need its own version of every reasoning rule (thresholds, categories, effects). Rerunning the real closure gives the exact answer for distance 1 with no new rules.
- **Allow any single addition, made things included.** Then nearly everything is one step away (add the thing itself, or its last missing input), which tells the user nothing.
