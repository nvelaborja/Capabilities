# 0018. Rank items by tech level

- **Status:** Accepted
- **Date:** 2026-11-05

## Context

The UI often has more items to show than fit: a thing's missing dependencies, a node's neighbours on the graph, the full dependency list. [ADR 0020](0020-show-a-bounded-number-of-items.md) shows the top few and summarizes the rest. That needs an order that puts the most advanced, most informative items first, and primitives like wood, fire and clay last.

The first idea was the number of direct inputs (in-degree). It doesn't measure how advanced something is: a steel spear has only a few direct inputs (steel, wood) but sits high in the hierarchy, while fire also has few.

## Decision

We will rank by **tech level**: the length of the shortest chain of steps from primitive materials, highest first.

- Natural materials have level 0.
- A route's level is the highest level among its requirements.
- A thing's level is 1 + the lowest level among its routes, because the easiest way defines how advanced it is.
- A category's level is the lowest among its members. An effect requirement's level is the lowest among the effect routes that can meet its threshold. An action's level is 1 + the lowest among the verb routes that can perform it.
- Levels are computed by repeated relaxation until nothing changes, which handles cycles (fire needs fuel, charcoal needs fire).
- Ties are broken by the number of things it certainly needs (a transitive in-degree), then alphabetically.
- Things with no known route and no natural origin have no level and sort last.

The server computes levels once at startup and includes them in the graph data. Tech level only **orders** items. It never decides whether an item is shown; that depends only on how many items there are ([ADR 0020](0020-show-a-bounded-number-of-items.md)).

## Consequences

- "Missing: bloom iron (level 3), iron ore (level 0)" puts the informative item first.
- Levels can also guide the graph layout (columns by level) and give the public an intuitive "tech level" number.
- Adding a new, easier route lowers a thing's level. That is correct, but levels shown to users can change as data grows.

## Alternatives considered

- **Direct in-degree.** Doesn't reflect height in the hierarchy (see context).
- **Total number of certain prerequisites only.** Closer, but it rewards breadth (things with many cheap inputs) over depth. It is kept as the tie-breaker.
- **Longest chain instead of shortest.** Would rank things by their hardest route, not how hard they are to reach.
