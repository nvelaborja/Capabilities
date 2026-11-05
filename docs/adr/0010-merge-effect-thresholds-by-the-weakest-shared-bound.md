# 0010. Merge effect thresholds by the weakest shared bound

- **Status:** Accepted
- **Date:** 2026-11-04 (recorded 2026-11-05)

## Context

When every route to something needs the same effect at different levels, backward inference has to say what is certainly needed. Steel's routes need heat ≥ 1100 °C for 24 h and ≥ 1200 °C for 24 h (counting what bloom iron needs).

## Decision

We will keep the **weakest bound shared by every route**, quantity by quantity. Within one route, the strongest bound applies. For steel, the certain need is ≥ 1100 °C for ≥ 24 h.

## Consequences

The result is sound (each route's own bound implies it), but it has side effects we may revisit:

- **It understates.** The merged bound can be weaker than every real route's.
- **It mixes quantities across routes.** Temperature may come from one route and duration from another.
- **It drops quantities** that only some routes constrain.
- **It only applies to effects.** Things, categories and actions are intersected exactly.
- **It feeds forward.** Implied effect levels count as achieved ([0006](0006-separate-selected-implied-and-reachable.md)), so any understatement carries into what is reachable.

The full explanation is in [docs/data-format.md](../data-format.md#merging-effect-thresholds).

## Alternatives considered

- **Keep one bound per route ("≥ 1100 °C/24 h or ≥ 1200 °C/24 h").** Exact, but implied needs become disjunctions, which complicates every consumer.
- **Pick the strongest bound.** Unsound: it claims more than the evidence supports.
