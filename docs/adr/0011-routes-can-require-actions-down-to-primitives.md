# 0011. Routes can require actions, built down to primitives

- **Status:** Accepted
- **Date:** 2026-11-04 (recorded 2026-11-05)

## Context

Many routes need an ability rather than a thing: making charcoal needs cut wood, and making rope needs cut plant fiber. Without this, the graph stopped at "wood" and hid the dependency chain that every civilization shares.

## Decision

- Requirements can have the role `action`, with a verb and a target, such as `{ role: action, verb: cut, target: wood }`.
- Verb routes can limit their targets with `applies_to` (chopping applies to plant material).
- The graph is built down to primitive roots: fieldstone → knapped stone chopper → cut wood → fire.

## Consequences

- Cutting wood and making fire are common ancestors of almost everything that needs heat or wooden parts. The one deeper root is knapping a stone tool.
- Questions like "what would it take?" bottom out in ubiquitous materials, as intended.
- Hub nodes (wood, fire) touch most of the graph, which visualizations must handle.

## Alternatives considered

- **Treat wood and fire as free.** Simpler, but it hides the shared foundation, which is itself a finding.
