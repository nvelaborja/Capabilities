# 0017. UI selection model: implicit selection, history and shareable state

- **Status:** Accepted; the contents of the two lists superseded by [0025](0025-detail-pane-below-graph-and-chip-lists.md)
- **Date:** 2026-11-05

## Context

In the UI, users build up a selection: a preset such as Middle Kingdom Egypt, plus their own additions and removals. Selecting something extreme (a hydrogen bomb) should pull in a large set of prerequisites, and should make many other things (a steel axe) reachable. Users will experiment, so mistakes must be cheap to undo, and results should be easy to share.

## Decision

**Implicit selection.** Selecting something also selects, implicitly, everything it certainly needs: what **every** route to it requires, recursively ([0006](0006-separate-selected-implied-and-reachable.md)). When there are alternatives, none of them is selected; only what they share.

**Two lists in one right-hand pane**, split horizontally:

1. **Selected** (top): the user's explicit selections and the implied ones, grouped by type, then sorted alphabetically. Implied items are marked as such and say what needs them. They can't be removed directly; the user removes what implies them instead.
2. **Reachable** (bottom): what could be made from the selection, with the same formatting. Near misses ("one step away") and trade warnings appear with it.

Each list scrolls on its own. The preset dropdown sits above both lists.

**What can be selected:** concrete things (materials, artifacts) and actions (cut granite). Categories ("any iron ore") and techniques can't be selected.

**Presets replace the selection.** Choosing a preset wipes the current list. If the user has edited the list since the last preset was loaded, we ask for confirmation first.

**Undo and redo.** Every change (add, remove, load preset, clear) is a step in a history stack, with buttons and keyboard shortcuts (⌘Z / ⇧⌘Z, Ctrl on other systems).

**Shareable links.** The URL holds the state as a preset plus the user's additions and removals, such as `?preset=middle-kingdom-egypt&add=hematite`. It is updated without adding browser-history entries; undo/redo handles history.

## Consequences

- One list answers "what did they have, for certain?", and the other "what could they have made?".
- Links encode changes to a preset, so they stay short, but their meaning follows the preset if its data changes later. That is acceptable for exploration. Citable snapshots would need a version in the link.
- The server must say, for each implied item, which selections imply it.

## Alternatives considered

- **Show implied items in a separate third list.** Clearer separation, but it splits "what they had" across two places. A marker in the same list keeps the distinction visible.
- **Full item list in the URL.** Stable meaning, but long links.
- **Use browser back/forward as undo.** Mixes navigation with editing, and every click would pile up history entries.
