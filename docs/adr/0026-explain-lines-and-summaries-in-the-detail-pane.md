# 0026. Explain lines, summary nodes and know-how in the detail pane

- **Status:** Accepted; summary nodes removed by [0030](0030-hide-extra-lines-focus-on-certain-needs-group-actions.md)
- **Date:** 2026-11-05
- **Supersedes:** "expand in place when clicked" for summary nodes in [0024](0024-fold-busy-nodes-links-into-summary-nodes.md)

## Context

Review of phase 4 found three gaps. Clicking a summary node ("4 other materials") made lines appear somewhere else on the graph with no explanation, which was confusing. Lines have different styles and threshold labels, but nothing explained them. And know-how chips (quenching, smithing) in the side pane opened a detail pane that couldn't load, because only drawn kinds could be explained.

## Decision

- **Everything clickable opens the detail pane**, with the same three columns read left to right (ADR 0025):
  - **A node:** what it needs, what it is, and what it leads to (unchanged).
  - **A line:** **From** (the source, and in each route behind the line its role, threshold, whether it is met and why), **The line** (what its style and label mean, why it is drawn strong or faint, and each route in full), and **To** (the target). An "is a" line says the member is a kind of the category, and which routes need any member. The API gains `POST /api/explain-edge`.
  - **A summary node:** whose links it holds and which way they run, the folded items as chips, and a **Show these N links** button that unfolds them and then opens the hub. Clicking a summary no longer unfolds it directly.
- **Summary nodes name their hub and direction:** "Heat → 4 more materials", "3 more tools → Steel". Their dashed link to the hub is drawn stronger than ordinary idle lines.
- **Know-how has its own view:** what it is, the routes it describes ("Used in", with what each makes), and what those lead to. Its status is "implied" when every route to a selection shares it, otherwise as reachable as the best route it describes. It still never gates anything ([0005](0005-know-how-never-gates-reachability.md)).
- **Items in the detail pane and the Expand all dialog are chips**, like the side pane and the graph: type strip with emoji, status border. The ✓ ✗ ? marks stay beside requirements, because a requirement can be unmet even when the item is reachable (heat, but not hot enough).
- Lines and summaries take part in the breadcrumb like nodes (`edge:heat|steel`, `summary:out:heat:material`).

## Consequences

- Every mark on the graph can be explained with one click, which matters for a public audience.
- Unfolding a summary takes two clicks instead of one, but it says what will happen first.
- One more endpoint, built from the same explainer as `/api/explain`, so reasons stay consistent.

## Alternatives considered

- **Keep click-to-unfold, and add a tooltip.** Hover-only information breaks [0019](0019-desktop-first-mobile-ready.md).
- **Drop summary nodes.** Hubs would get unreadable as the data grows; folding stays, now explained.
- **Show line details in a popover on the graph.** Too little room for the routes behind a line.
