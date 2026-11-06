# 0025. Put the detail pane under the graph, and show the side pane as chips

- **Status:** Accepted; status wording superseded by [0028](0028-floating-resizable-panes-and-neutral-wording.md), which also makes the panes resizable; Could do grouped by verb by [0030](0030-hide-extra-lines-focus-on-certain-needs-group-actions.md)
- **Date:** 2026-11-05
- **Supersedes:** the contents of the two lists in [0017](0017-ui-selection-model.md)

## Context

After using phase 4, three things stood out. The detail pane on the left took width from the graph, and the graph reads left to right. The right-hand lists were a wall of text with collapsible type headings. And mixing implied items into the Selected list made it hard to see what the user had actually chosen.

## Decision

- **The detail pane runs along the bottom of the graph**, not under the right-hand pane, and only while something is open. Like the graph, it reads left to right in three columns: what the node needs (its routes, or a category's members), what it is (description, numbers, sources), and what it leads to. Each column scrolls on its own; narrow screens stack them.
- **The legend sits in the graph toolbar (top left), hidden until opened.**
- **The side pane shows chips drawn like graph nodes**: the type's coloured strip and emoji on the left, and the status border (selected, implied, maybe, one step away) from [0022](0022-type-strip-with-emoji-on-neutral-nodes.md). Chips wrap, sorted by type and then name, with each type starting a new line. There are no type headings, since the emoji names the type.
- **Selected (top) holds only what the user chose.** Each chip has × to remove it.
- **The bottom list, "Implied and reachable", holds everything that follows from the selection**, in sections: Implied (they must have had these), Could make, Could do, and One step away (with what is missing). Nothing appears in both lists.

The rest of 0017 (implicit selection, presets, undo/redo, links) is unchanged.

## Consequences

- The graph keeps its full width, and the detail pane mirrors its direction: inputs left, outputs right.
- The top list answers "what did I choose?" at a glance; "what must they have had?" moves down with the other consequences.
- What implies an implied item is no longer printed in the list. The chip's tooltip and the detail pane show it, so it is never hover-only ([0019](0019-desktop-first-mobile-ready.md)).
- Lists and graph share one visual language, so the legend explains both.

## Alternatives considered

- **Keep implied items in Selected with a badge** (0017). Mixes choices with consequences.
- **Detail pane across the full width, under the side pane too.** Would shorten the side pane's lists.
- **Keep collapsible type groups with chips inside.** The emoji already shows type, and the headings cost space.
