# 0024. Fold a busy node's extra links into summary nodes

- **Status:** Accepted
- **Date:** 2026-11-05
- **Refines:** the graph half of [0020](0020-show-a-bounded-number-of-items.md)

## Context

[ADR 0020](0020-show-a-bounded-number-of-items.md) bounds a node's neighbourhood on the graph: past *N* neighbours, the rest collapse into summary nodes ("43 other materials"). It was written when the graph laid nodes out freely. Since [ADR 0023](0023-draw-requirements-straight-to-products.md), every node has a fixed place in its tech-level column, and most nodes are neighbours of several hubs at once. Hiding a node because one hub has too many neighbours would hide it for every other node too, and would leave gaps in the columns.

## Decision

- **Fold links, not nodes.** When a node links to more than *N* others in one direction (what it helps make, or what it needs), it keeps its links to the top *N* by tech level ([ADR 0018](0018-rank-dependencies-by-tech-level.md)). Its other links fold into one summary node per type ("4 other tools and products"), joined to the hub by a single dashed link. The neighbours themselves stay in their columns.
- An edge stays hidden while any summary holding it is folded, so it never appears half-attached.
- **Summary nodes sit in the next column** (the previous one for inputs), below the real nodes, and expand in place when clicked: the summary disappears, its links come back, and nothing else moves. "Expand all" in the graph toolbar shows every link; "Summarise" folds them again.
- Summary nodes have no type strip, can't be selected, and are left out of the clicked node's highlighted neighbourhood.
- **Focus mode** (showing only what feeds a node, and what it directly makes) summarises only what it shows.
- *N* is the same single setting as for lists (`web/src/lib/bounded.ts`, starting at 8).

## Consequences

- Hubs like heat (16 products) and wood (10) stay readable, and no node is ever hidden for being busy.
- A node whose only link folds away appears unconnected until the summary is expanded or the hub is clicked in the detail pane, which always lists everything.
- Expanding re-uses current positions; "Expand all" and focus mode re-run the column layout.

## Alternatives considered

- **Collapse the neighbour nodes themselves**, as 0020 first described. Conflicts with fixed columns: a node folded for one hub would vanish for every other.
- **No graph bounding, rely on faint edges.** Works today, but hubs grow with the data, and their highlighted neighbourhoods become unreadable.
