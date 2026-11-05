# 0021. Colour shows type, border shows status; lay the graph out as a tech tree

- **Status:** Accepted
- **Date:** 2026-11-05

## Context

The first graph view used shapes for node types (ellipse for materials, hexagon for actions, diamond for categories, and so on) and fill and border for status. On review, the mix of shapes looked busy and harder to scan than a uniform set of boxes. The layout also only loosely followed tech levels, so the "primitive to advanced" story didn't read at a glance. The page needed light and dark themes that viewers can choose, not only the system setting.

## Decision

- **Every node is a rounded rectangle**, except route junctions, which stay small dots because they are connectors, not things.
- **Colour shows type.** Each type (material, tool or product, action, category, effect) has its own hue from a colour-blind-safe set based on Okabe & Ito. Each hue has a pale tint, a strong fill, a label colour for that fill, and a border colour, defined for both themes in `web/src/theme.css`. Categories are also italic, as a second cue.
- **Border and fill show status.** Each status has its own combination of border width, border style and opacity, so status never depends on colour:

  | Status | Border | Fill |
  |---|---|---|
  | Selected | 3px solid, text colour, bold label | strong |
  | What-if | 4px double | strong |
  | Implied | none | strong |
  | Reachable | 2px solid | tint |
  | Maybe | 2px dotted | tint |
  | One step away | 2px dashed | tint |
  | Out of reach | 1px, faded to 45% | plain |

- **The graph is a technology tree.** Each node sits in its tech-level column ([ADR 0018](0018-rank-dependencies-by-tech-level.md)), with primitives on the left and a "Level N" heading above each column. Dagre gives a first order within columns; barycentre sweeps then reduce crossings, and columns are stacked tightly. Nodes without a level (verb routes, things with no known route) go one column right of what feeds them.
- **Theme switch.** Auto (follows the system), Light, or Dark, in the header. The choice is remembered per viewer and applied before the first paint.

## Consequences

- The graph is calmer, and the left-to-right story is explicit.
- **Type relies on colour** (plus italics for categories). Colour-blind viewers get a palette chosen for them, and the detail pane (phase 4) names each node's type. If this proves insufficient, a small type tag on each node is the next step.
- Strict columns produce some long edges, for example a saw (level 7) that can also cut wood (level 2). Bounding hub neighbourhoods ([ADR 0020](0020-show-a-bounded-number-of-items.md)) will reduce the clutter.
- All colours live in CSS variables, so a hosted version or a design system can restyle the graph without touching the code.

## Alternatives considered

- **Shapes for type** (the first version). Busier, and status borders were harder to read on irregular shapes.
- **Border style for type and colour for status.** Status must not depend on colour, and border styles were already carrying it.
- **Dagre's own ranks, with levels only as hints.** Ingredients with nothing feeding them drifted right, so columns didn't mean tech levels.
- **Absolute row positions from a constraint solver.** Better crossing reduction, but heavier and not needed at this size.
