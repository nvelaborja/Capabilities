# 0023. Draw requirements straight to products, and order columns by type and name

- **Status:** Accepted
- **Date:** 2026-11-05
- **Supersedes:** the route-junction drawing and dagre layout in [0015](0015-build-the-web-front-end-with-react-and-cytoscape.md), and the crossing-reduction ordering in [0021](0021-colour-for-type-border-for-status-tech-tree-layout.md)

## Context

The graph drew every route as a small junction node ("Casting a copper saw blade") between a thing and its requirements, to show "any of these ways" versus "all of these". On review, the junctions added a lot of density for little benefit: which requirements belong together is detail, and the detail pane can show it. The order of nodes within each tech-level column came from dagre plus barycentre sweeps, which minimised crossings but made the columns hard to scan.

## Decision

- **No route junctions on the graph.** Each requirement is drawn straight to what its route makes (or to the action a verb route performs). When several routes link the same pair, they merge into one edge that keeps every route, role and threshold label. An edge is "live" if any route behind it works. Edges that only lead to byproducts (slag) are dotted.
- **The API still returns routes** (`/api/graph`, `/api/explain`), and the detail pane lists each way of making something with its requirements.
- **Columns are sorted by type, then alphabetically:** materials, tools and products, actions, any of a kind, effects. This matches the side-pane lists. Type groups have a little extra space between them.
- **dagre is removed.** Tech levels decide the columns and sorting decides the order, so no layout engine is needed.

## Consequences

- The graph is much less dense, and columns are predictable and easy to scan.
- The graph no longer shows which requirements belong to which route, or that there are alternatives. That moves to the detail pane (phase 4). Until then, the node card shows what is missing per route for things one step away.
- More edges cross, since order no longer tries to avoid crossings. Faint idle edges and click-to-highlight keep this readable.
- One fewer dependency, and about 30 kB less JavaScript.

## Alternatives considered

- **Keep junctions but hide their labels.** Still dense.
- **Keep crossing reduction within type groups.** Possible later if crossings become a problem, but scanning by name matters more for a public audience.
