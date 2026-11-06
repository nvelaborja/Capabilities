# 0028. Float the panes with resizable gaps, and word statuses without assuming a group

- **Status:** Accepted
- **Date:** 2026-11-06
- **Supersedes:** the status wording "(they must have had these)" in [0025](0025-detail-pane-below-graph-and-chip-lists.md)

## Context

The header, graph, side pane and detail pane ([0025](0025-detail-pane-below-graph-and-chip-lists.md)) sat edge to edge with fixed sizes. Users want more room for whichever pane they are reading: a long route checklist, or a wide graph.

The interface also said "they" throughout: "Implied (they must have had it)", "Reachable (they could have made it)". A selection need not describe a civilisation. It can be any set of things someone wants to reason from.

## Decision

We will draw each pane as a floating card with small rounded corners on a slightly darker backdrop, with a gap between panes.

- **The gaps beside the side pane and the detail pane are splitters.** Drag one to resize the pane, or focus it and use the arrow keys (Shift for bigger steps), Home and End. Double-click puts the pane back to its default size. A short grip always shows in the middle of each gap, so resizing never depends on hover ([0019](0019-desktop-first-mobile-ready.md)); it becomes a full accent line while hovered, focused or dragged.
- Sizes are remembered per browser. They are a convenience, so if storage is unavailable the defaults apply. The graph always keeps at least 320 px of width and 160 px of height.
- The detail pane's columns respond to the pane's own width (a container query), not the window's, since the pane can now be narrow on a wide screen.

We will word statuses in terms of **the selection**, not a group:

| Before | After |
|---|---|
| Implied (they must have had it) | Implied (required by the selection) |
| Reachable (they could have made it) | Reachable (can be made from the selection) |
| They must have had these | Required by the selection |
| They must have had this: it is needed by … | Required by the selection: … needs it |
| Things they made or had, or actions they did | Things made or had, or actions done |

Data that really is about a group, such as a profile's description or the Egypt worked example, keeps its wording.

## Consequences

- Users can give the graph or the details more room, and the layout comes back the same next time.
- The gaps cost 8 px each. The panes no longer share borders, which makes each one read as its own area.
- Statuses read the same whether the selection is a civilisation, a workshop or a thought experiment.

## Alternatives considered

- **Fixed sizes with a few presets** (compact, balanced, wide details). Fewer controls, but users can't pick the size they need.
- **Thin splitters on shared borders.** Saves space, but the 1 px border is a hard target to grab, and the user asked for visible gaps.
- **"Required by your selection".** Also neutral, but "the selection" reads better in shared links, where the viewer didn't make it.
