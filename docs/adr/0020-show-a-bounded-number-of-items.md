# 0020. Show one level at a time and a bounded number of items

- **Status:** Accepted; graph summaries refined by [0024](0024-fold-busy-nodes-links-into-summary-nodes.md), then replaced by hidden lines in [0030](0030-hide-extra-lines-focus-on-certain-needs-group-actions.md)
- **Date:** 2026-11-05

## Context

Dependency lists explode as the graph grows. A hydrogen bomb certainly needs hundreds of things, and hubs like wood, clay and fire connect to most of the graph. Showing everything at once makes the detail pane and the graph unreadable. Hiding things because they are primitive (common materials) would make the AND requirements look incomplete, and would be a judgment about what matters.

## Decision

**One level at a time, with drill-down.** For a thing out of reach, the detail pane shows only its **first-degree** dependencies: the direct requirements of each route, each marked met (✓), missing (✗) or unknown (?), with the reason. Clicking a dependency opens *its* details, so the user can drill down to see what it is missing. A breadcrumb trail (Steel › Bloom iron › Iron ore) leads back.

**"Expand all dependencies"** shows the complete list on request: everything the thing certainly needs at every depth, split into have and missing, grouped by type.

**A bounded number of items, decided by count only.** Whenever a list or a node's neighbourhood on the graph has more than *N* items, we show the top *N* by tech level ([ADR 0018](0018-rank-dependencies-by-tech-level.md)). The rest are summarized by type ("43 other materials", "12 other tools"). Clicking a summary, or "Expand all", shows everything. Whether an item is shown never depends on what kind of item it is or how primitive it is; only on how many items there are. *N* is a single setting, starting at 8, and tuned by eye.

On the graph, the summaries are summary nodes ("43 other materials") that expand in place when clicked.

## Consequences

- The detail pane stays short and answers "what's missing *right here*?". Users follow the chain one step at a time, which also teaches how the graph fits together.
- Hubs stay visible but bounded, and nothing is hidden for being "common".
- The full picture is always one click away.
- Summary nodes need custom handling in the graph (they are not real nodes and can't be selected).

## Alternatives considered

- **Show every certain dependency, top N with "see all".** Long lists, mostly of things that are themselves blocked by one deeper item.
- **Hide or fade common materials.** A judgment about importance; makes AND requirements look incomplete.
- **Scrolling lists only.** Fine for the right-hand pane (which keeps scrolling, per [ADR 0017](0017-ui-selection-model.md)), but doesn't solve the graph.
