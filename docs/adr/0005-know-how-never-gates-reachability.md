# 0005. Know-how never gates reachability

- **Status:** Accepted
- **Date:** 2026-11-04 (recorded 2026-11-05)

## Context

The first design treated techniques (smelting, casting) as requirements. Techniques could only come from the user's starting set, never be derived. That made results depend on modeling who "knew" what, which can't be sourced reliably and isn't the question we are asking. The question is what was **within reach**: a civilization with enriched uranium and the other ingredients is capable of an atomic bomb, whether or not anyone built one.

## Decision

We will never let know-how block a route.

- A route is within reach if its material, tool, effect and action requirements are met.
- Techniques are descriptive labels on routes (`techniques: [...]`), not requirements.
- **Having something implies the capability of making it.** The techniques shared by every route to a selected thing are reported as implied. For example, having steel implies iron smelting.

This replaces the first design's rule that techniques are never derived.

## Consequences

- Results depend only on physical prerequisites, which can be sourced.
- **Regional resources become the main gate.** Anything made only from ubiquitous materials (wood, clay, stone, sand) is reachable by everyone, including bellows and fire pistons.
- The tool will say a group "could" make things nobody believes they made. That is intended: the tool reports capability, not history.

## Alternatives considered

- **Techniques as requirements, set by the user.** Unsourceable, and results would mostly reflect the user's assumptions.
- **Techniques derived from experience.** Speculative and hard to justify.
