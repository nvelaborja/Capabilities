# 0030. Hide busy nodes' extra lines without placeholders, focus on certain needs, and group actions by verb

- **Status:** Accepted
- **Date:** 2026-11-06
- **Supersedes:** summary nodes ([0024](0024-fold-busy-nodes-links-into-summary-nodes.md), and their detail view in [0026](0026-explain-lines-and-summaries-in-the-detail-pane.md)); keeping the Selected pane's size in [0029](0029-split-the-side-column-into-two-resizable-panes.md)

## Context

Four things came out of the third review.

- **Summary nodes confused people.** "Heat → 4 more materials" stood for hidden *lines*, not things. Its items were already on the graph, in other columns, so clicking it showed things that were already visible. It also sat in a tech-level column, which made it look like a thing at that level.
- **Focus mode showed most of the graph.** It followed everything that *could* feed a node, through every route. Heat, fire and "any edged tool" pulled in 57 of 70 nodes for steel.
- **"Could do" was a wall of 48 chips**, mostly one verb applied to many materials.
- **A Selected size set by hand outlived the selection it suited.** After adding or removing items, the pane was too big or too small.

## Decision

- **No placeholder nodes.** A busy node still draws lines only to its 8 most advanced neighbours in each direction ([0018](0018-rank-dependencies-by-tech-level.md), [0020](0020-show-a-bounded-number-of-items.md)), and its other lines are hidden. Clicking the node, or the node at the other end, draws all of its lines while it is selected. **Expand all** draws every line. The detail pane always lists everything.
- **Focus mode shows what a node certainly needs.** It shows the node, everything it needs whichever way it is made, at every depth (the Expand all set, [0006](0006-separate-selected-implied-and-reachable.md)), and what it directly makes, and hides everything else. A category's members count as its needs, since it stands for any of them. `GET /api/graph` sends each node's certain needs as `needs`. Steel's focus drops from 57 nodes to 13.
- **"Could do" groups actions by verb.** A verb with several targets becomes one chip that counts them, such as "✋ Cut · 15 materials (1 maybe) ▸". Clicking it lists the targets as chips underneath. A verb with one target stays a plain chip.
- **The Selected pane fits each new selection.** Any change to the selection, undo included, resets the pane to fit its chips, up to half the column. A size dragged by hand lasts until the next change and isn't remembered across visits.

## Consequences

- The graph has only real things on it. The only cue that lines are hidden is in the legend, so users may not notice until they click a busy node or use Expand all. If that proves a problem, we can add a small "+4 lines" note to busy nodes.
- Focus mode no longer shows alternatives: steel's crucible route needs a crucible, but the carburizing route doesn't, so the crucible is hidden. The detail pane still shows every route.
- Focus needs come from the server, so they follow the reasoner's rules exactly. The graph response grows by one list per node, about 175 ids today.

## Alternatives considered

- **Keep summary nodes, with clearer labels.** Two rounds of relabelling didn't make them clear: a node standing for lines is the problem.
- **Draw every line all the time.** This is what Expand all shows. Hubs like heat make it a tangle, so it stays opt-in.
- **Focus on everything that could feed a node.** That is the old behaviour, which showed most of the graph.
- **Group "Could do" by target instead of verb.** Fewer groups, but "what can I do to granite?" is the less common question.
