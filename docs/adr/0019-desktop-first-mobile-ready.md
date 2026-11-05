# 0019. Build desktop-first, without blocking mobile

- **Status:** Accepted
- **Date:** 2026-11-05

## Context

A graph explorer with side panels is far easier to build and use on a large screen. The public audience will eventually include phones, but supporting them now would slow the first version.

## Decision

The first version targets desktop browsers only. We will avoid choices that make mobile harder later:

- The page layout uses CSS grid areas, so panels can later stack or become bottom sheets without restructuring components.
- No information is available **only** on hover. Everything shown on hover can also be reached by click or tap.
- Interactions use pointer events and single clicks, not double-click or right-click menus. Cytoscape supports touch already.
- Sizes use relative units, not fixed pixel widths, except for minimum widths.
- Keyboard shortcuts are conveniences; every action also has a visible control.

## Consequences

- Faster first version.
- A phone layout later is mostly CSS and a few panel components, not a rewrite.

## Alternatives considered

- **Responsive from day one.** Doubles the layout and testing work before the interaction design has settled.
