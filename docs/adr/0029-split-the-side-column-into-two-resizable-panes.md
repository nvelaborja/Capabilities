# 0029. Split the side column into two resizable panes

- **Status:** Accepted
- **Date:** 2026-11-06
- **Supersedes:** "two lists in one right-hand pane" in [0017](0017-ui-selection-model.md)

## Context

The side pane held the preset, an optional trade warning, Selected and Implied and reachable, in one grid that expected four rows. Without a warning the rows shifted: Selected shrank to fit, and Implied and reachable kept only half the height, leaving an empty gap below its list. Splitting the height evenly also wasted space: a selection of one item took half the column.

## Decision

We will draw the side column as **two floating panes** with a resizable gap between them, styled and resized like the others ([0028](0028-floating-resizable-panes-and-neutral-wording.md)):

- **Selected** (top) holds the preset, any warning and the Selected list. By default it is as tall as its content, up to half the column, and then its list scrolls.
- **Implied and reachable** (bottom) takes the rest of the height.
- **The gap between them is a splitter.** Drag it, or focus it and use the arrow keys (down grows Selected), Home and End. Double-click returns Selected to fitting its content. The size is remembered per browser, and the pane below always keeps at least 9rem.
- Each pane lays out its parts in a column, so an optional part such as the warning can come and go without moving the others.

## Consequences

- A short selection leaves most of the column to what follows from it. A long one stops at half and scrolls.
- Once the user sets a size, it stays fixed as the selection changes, until they double-click the gap.

## Alternatives considered

- **Keep one pane and fix the grid rows.** Fixes the bug, but the even split still wastes space and can't be adjusted.
- **Collapse Selected into a summary line.** Saves space, but hides the chips the user works with most.
