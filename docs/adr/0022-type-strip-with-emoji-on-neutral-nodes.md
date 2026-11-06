# 0022. Show type with a coloured strip and emoji on neutral nodes

- **Status:** Accepted
- **Date:** 2026-11-05
- **Supersedes:** the node-colouring part of [0021](0021-colour-for-type-border-for-status-tech-tree-layout.md) (fully coloured nodes, and strong fills for things they had). The tech-tree layout and theme switch in 0021 stand.

## Context

ADR 0021 coloured whole nodes by type: a pale tint normally, and a strong fill for things they had. On review, whole-node colour was loud and made labels harder to read, and type was told apart by colour alone.

## Decision

- **Every node has the same neutral surface:** off-white with black text in light mode, dark grey with light text in dark mode (`--node-bg`, `--node-text`).
- **Type is a strip on the left** in the type's colour, with an emoji centred in it: 🪨 material, 🔨 tool or product, ✋ action, 🗂️ any of a kind, 🔥 effect. The emoji is a second cue besides colour, so type no longer relies on colour alone.
- **Status is the border** around the whole node, in the type's colour. Each status has its own width, style and opacity:

  | Status | Border |
  |---|---|
  | Selected | 3px solid, bold label |
  | What-if | 4px double, bold label |
  | Implied | 2px solid |
  | Reachable | 1px solid |
  | Maybe | 2px dotted |
  | One step away | 2px dashed |
  | Out of reach | 1px grey, faded to 45% |

- Cytoscape draws nodes on a canvas, so the strip and emoji are two background images (a stretched SVG rectangle, and an SVG with the emoji), clipped to the node's rounded shape. The label is shifted right to clear the strip.

## Consequences

- Labels are always black on off-white (or light on dark grey), so they are easier to read.
- "Had it" (selected, implied) is now shown only by the border, not by fill. Selected is still bold, which keeps it easy to spot.
- Emoji rendering depends on the viewer's system fonts. Every current desktop OS has colour emoji; the strip colour still shows the type where they don't.
- The legend draws small HTML versions of nodes from the same variables, emoji and border rules.

## Alternatives considered

- **Fully coloured nodes** (ADR 0021). Loud, with type by colour alone.
- **HTML overlays for nodes** (e.g. a node-HTML-label extension). Real inner elements, but they render outside the canvas, which is slower and complicates zooming and fading.
- **Icons from an icon font or SVG set** instead of emoji. Consistent across systems, but adds a dependency; emoji are enough for now.
