import type { StylesheetJson } from "cytoscape";

import type { DrawnKind } from "../api/types";

export const TYPED_KINDS: readonly DrawnKind[] = ["material", "artifact", "action", "category", "effect"];

/** One node type's colours (see theme.css): strong fill and its label colour, pale tint, and border. */
export interface TypeColours {
  fill: string;
  ink: string;
  tint: string;
  line: string;
}

/** Colours the graph needs, read from CSS custom properties so light and dark themes stay in one place. */
export interface GraphTokens {
  surface: string;
  text: string;
  muted: string;
  accent: string;
  edge: string;
  edgeLive: string;
  out: string;
  types: Record<DrawnKind, TypeColours>;
}

export function readTokens(root: Element = document.documentElement): GraphTokens {
  const computed = getComputedStyle(root);
  const read = (variable: string) => computed.getPropertyValue(variable).trim();
  const typeColours = (kind: DrawnKind): TypeColours => ({
    fill: read(`--type-${kind}-fill`),
    ink: read(`--type-${kind}-ink`),
    tint: read(`--type-${kind}-tint`),
    line: read(`--type-${kind}-line`),
  });
  return {
    surface: read("--surface"),
    text: read("--text"),
    muted: read("--text-muted"),
    accent: read("--accent"),
    edge: read("--edge"),
    edgeLive: read("--edge-live"),
    out: read("--out"),
    types: Object.fromEntries(TYPED_KINDS.map((kind) => [kind, typeColours(kind)])) as Record<DrawnKind, TypeColours>,
  };
}

/**
 * How each status looks, independent of type. Every status has its own combination of border width, border style
 * and opacity, so status never depends on colour alone. "Had it" statuses also get the type's strong fill.
 */
export const STATUS_LOOK = {
  selected: { "border-width": 3, "border-style": "solid", opacity: 1, hadIt: true },
  hypothetical: { "border-width": 4, "border-style": "double", opacity: 1, hadIt: true },
  implied: { "border-width": 0, "border-style": "solid", opacity: 1, hadIt: true },
  reachable: { "border-width": 2, "border-style": "solid", opacity: 1, hadIt: false },
  maybe: { "border-width": 2, "border-style": "dotted", opacity: 1, hadIt: false },
  near: { "border-width": 2, "border-style": "dashed", opacity: 1, hadIt: false },
  out: { "border-width": 1, "border-style": "solid", opacity: 0.45, hadIt: false },
} as const;

/**
 * Edges stay in the background until a node is clicked: faint when idle, a little stronger for routes that work
 * (live), clear for the clicked node's neighbourhood, and nearly gone for everything else while focused.
 */
export const EDGE_OPACITY = { idle: 0.12, live: 0.3, highlighted: 0.95, faded: 0.04 } as const;

const FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';

/** Every node is a rounded rectangle; its colour says what it is and its border says where it stands. */
export function buildStylesheet(t: GraphTokens): StylesheetJson {
  const typeRules: StylesheetJson = TYPED_KINDS.map((kind) => ({
    selector: `node.${kind}`,
    style: { "background-color": t.types[kind].tint, "border-color": t.types[kind].line },
  }));
  const statusRules: StylesheetJson = Object.entries(STATUS_LOOK).map(([status, look]) => ({
    selector: `node.status-${status}`,
    style: { "border-width": look["border-width"], "border-style": look["border-style"], opacity: look.opacity },
  }));
  const hadItRules: StylesheetJson = TYPED_KINDS.map((kind) => ({
    selector: ["selected", "hypothetical", "implied"].map((status) => `node.${kind}.status-${status}`).join(", "),
    style: { "background-color": t.types[kind].fill, color: t.types[kind].ink },
  }));

  return [
    // ---------------------------------------------------------------- base
    {
      selector: "node",
      style: {
        shape: "round-rectangle",
        label: "data(label)",
        width: "data(width)",
        height: "data(height)",
        "font-family": FONT,
        "font-size": 12,
        color: t.text,
        "text-valign": "center",
        "text-halign": "center",
        "text-wrap": "wrap",
        "text-max-width": "160px",
        "background-color": t.surface,
        "border-width": 1,
        "border-style": "solid",
        "min-zoomed-font-size": 7,
      },
    },
    ...typeRules,
    // Italic as a second cue for "any of a kind", besides colour.
    { selector: "node.category", style: { "font-style": "italic" } },
    { selector: "node.ubiquitous", style: { "font-size": 11 } },
    {
      // Route junctions stay small dots: they are connectors, not things.
      selector: "node.route",
      style: {
        shape: "ellipse",
        "background-color": t.edge,
        "border-width": 0,
        "font-size": 8,
        color: t.muted,
        "text-valign": "bottom",
        "text-margin-y": 3,
        // Route names only appear once zoomed in, to keep the overview readable.
        "min-zoomed-font-size": 12,
      },
    },
    {
      selector: "node.level-label",
      style: {
        shape: "round-rectangle",
        "background-opacity": 0,
        "border-width": 0,
        color: t.muted,
        "font-size": 13,
        "font-weight": "bold",
        "min-zoomed-font-size": 6,
      },
    },
    {
      selector: "edge",
      style: {
        width: 1,
        "line-color": t.edge,
        "target-arrow-color": t.edge,
        "target-arrow-shape": "triangle",
        "arrow-scale": 0.6,
        "curve-style": "bezier",
        label: "data(label)",
        "font-family": FONT,
        "font-size": 8,
        color: t.muted,
        "text-rotation": "autorotate",
        "text-background-color": t.surface,
        "text-background-opacity": 0.85,
        "text-background-padding": "1px",
        "min-zoomed-font-size": 10,
        opacity: EDGE_OPACITY.idle,
      },
    },
    { selector: "edge.role-tool", style: { "line-style": "dashed" } },
    { selector: "edge.role-action", style: { "line-style": "dotted" } },
    { selector: "edge.byproduct", style: { "line-style": "dotted" } },
    { selector: "edge.is_a", style: { width: 0.75, "line-style": "dashed", "target-arrow-shape": "none" } },
    { selector: "edge.live", style: { "line-color": t.edgeLive, "target-arrow-color": t.edgeLive, opacity: EDGE_OPACITY.live } },

    // ---------------------------------------------------------------- statuses
    ...statusRules,
    ...hadItRules,
    { selector: "node.status-selected, node.status-hypothetical", style: { "border-color": t.text, "font-weight": "bold" } },
    { selector: "node.status-out", style: { "background-color": t.surface, "border-color": t.out, color: t.muted } },
    { selector: "node.route.route-yes", style: { "background-color": t.accent } },
    { selector: "node.route.route-maybe", style: { "background-color": t.surface, "border-width": 1.5, "border-color": t.accent } },
    { selector: "node.route.route-no", style: { "background-color": t.out } },

    // ---------------------------------------------------------------- focus (clicking a node)
    { selector: "node.focused", style: { "underlay-color": t.accent, "underlay-opacity": 0.25, "underlay-padding": 6 } },
    { selector: "node.faded", style: { opacity: 0.12 } },
    { selector: "edge.faded", style: { opacity: EDGE_OPACITY.faded } },
    // Edge labels (heat thresholds) show for the clicked node's edges at any zoom.
    { selector: "edge.highlighted", style: { opacity: EDGE_OPACITY.highlighted, width: 1.5, "min-zoomed-font-size": 0 } },
    { selector: "node:selected", style: { "overlay-opacity": 0 } },
  ];
}
