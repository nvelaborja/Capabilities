import type { StylesheetJson } from "cytoscape";

import type { DrawnKind, Status } from "../api/types";
import { STRIP_WIDTH } from "./elements";
import { FOLDED, OUTSIDE, REVEALED } from "./focus";

export const TYPED_KINDS: readonly DrawnKind[] = ["material", "artifact", "action", "category", "effect"];

/** The emoji in each type's strip, a second cue besides colour. */
export const TYPE_ICONS: Record<DrawnKind, string> = {
  material: "🪨",
  artifact: "🔨",
  action: "✋",
  category: "🗂️",
  effect: "🔥",
};

export const ICON_SIZE = 16;

/** One node type's colours (see theme.css): strip fill and its text colour, pale tint, and border. */
export interface TypeColours {
  fill: string;
  ink: string;
  tint: string;
  line: string;
}

/** Colours the graph needs, read from CSS custom properties so light and dark themes stay in one place. */
export interface GraphTokens {
  surface: string;
  nodeBg: string;
  nodeText: string;
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
    nodeBg: read("--node-bg"),
    nodeText: read("--node-text"),
    text: read("--text"),
    muted: read("--text-muted"),
    accent: read("--accent"),
    edge: read("--edge"),
    edgeLive: read("--edge-live"),
    out: read("--out"),
    types: Object.fromEntries(TYPED_KINDS.map((kind) => [kind, typeColours(kind)])) as Record<DrawnKind, TypeColours>,
  };
}

export interface StatusLook {
  "border-width": number;
  "border-style": "solid" | "double" | "dotted" | "dashed";
  /** Dash and gap lengths, for a dashed border that needs more spacing than the default. */
  "border-dash-pattern"?: readonly [number, number];
  opacity: number;
}

/**
 * How each status looks. The border runs around the whole node in the type's colour; its width and style (and the
 * node's opacity) give every status its own look, so status never depends on colour alone. Selected labels are bold.
 * "One step away" is deliberately quiet (thin, sparse dashes, slightly faded): it sits between reachable and out.
 */
export const STATUS_LOOK: Record<Status, StatusLook> = {
  selected: { "border-width": 3, "border-style": "solid", opacity: 1 },
  hypothetical: { "border-width": 4, "border-style": "double", opacity: 1 },
  implied: { "border-width": 2, "border-style": "solid", opacity: 1 },
  reachable: { "border-width": 1, "border-style": "solid", opacity: 1 },
  maybe: { "border-width": 2, "border-style": "dotted", opacity: 1 },
  near: { "border-width": 1, "border-style": "dashed", "border-dash-pattern": [4, 6], opacity: 0.75 },
  out: { "border-width": 1, "border-style": "solid", opacity: 0.45 },
};

const svgUri = (svg: string) => `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;

/** A solid strip, stretched to the node's height. */
export function stripImage(colour: string): string {
  return svgUri(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${STRIP_WIDTH}" height="40" viewBox="0 0 ${STRIP_WIDTH} 40" preserveAspectRatio="none"><rect width="${STRIP_WIDTH}" height="40" fill="${colour}"/></svg>`,
  );
}

/** An emoji drawn as an image, so it can sit in the strip. */
export function iconImage(icon: string): string {
  return svgUri(
    `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32"><text x="16" y="17" font-size="24" text-anchor="middle" dominant-baseline="central">${icon}</text></svg>`,
  );
}

/**
 * Edges stay in the background until a node is clicked: faint when idle, a little stronger where a route that
 * works runs through them (live), clear for the clicked node's neighbourhood, and nearly gone for everything else while focused.
 */
export const EDGE_OPACITY = { idle: 0.12, live: 0.3, highlighted: 0.95, faded: 0.04 } as const;

const FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';

/**
 * Every node is a rounded rectangle on a shared surface. A coloured strip with an emoji on the left says what it
 * is, and the border around the whole node says where it stands (ADR 0022).
 */
export function buildStylesheet(t: GraphTokens): StylesheetJson {
  const typeRules: StylesheetJson = TYPED_KINDS.map((kind) => ({
    selector: `node.${kind}`,
    style: {
      "border-color": t.types[kind].line,
      "background-image": [stripImage(t.types[kind].fill), iconImage(TYPE_ICONS[kind])],
      "background-width": [`${STRIP_WIDTH}px`, `${ICON_SIZE}px`],
      "background-height": ["100%", `${ICON_SIZE}px`],
      "background-position-x": ["0px", `${(STRIP_WIDTH - ICON_SIZE) / 2}px`],
      "background-position-y": ["0%", "50%"],
      "background-fit": ["none", "none"],
      "background-repeat": ["no-repeat", "no-repeat"],
      "background-clip": ["node", "node"],
    },
  }));
  const statusRules: StylesheetJson = Object.entries(STATUS_LOOK).map(([status, look]) => ({
    selector: `node.status-${status}`,
    style: {
      "border-width": look["border-width"],
      "border-style": look["border-style"],
      ...(look["border-dash-pattern"] && { "border-dash-pattern": [...look["border-dash-pattern"]] }),
      opacity: look.opacity,
    },
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
        color: t.nodeText,
        "text-valign": "center",
        "text-halign": "center",
        // Centre the label in the space right of the strip.
        "text-margin-x": STRIP_WIDTH / 2,
        "text-wrap": "wrap",
        "text-max-width": "160px",
        "background-color": t.nodeBg,
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
      selector: "node.level-label",
      style: {
        shape: "round-rectangle",
        "background-opacity": 0,
        "border-width": 0,
        "text-margin-x": 0,
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
    // A busy node's extra lines hide until it, or the node at the other end, is clicked (ADR 0030). Outside focus mode
    // comes last, so it hides even a revealed line.
    { selector: `.${FOLDED}`, style: { display: "none" } },
    { selector: `edge.${REVEALED}`, style: { display: "element" } },
    { selector: `.${OUTSIDE}`, style: { display: "none" } },

    // ---------------------------------------------------------------- statuses
    ...statusRules,
    { selector: "node.status-selected, node.status-hypothetical", style: { "font-weight": "bold" } },
    { selector: "node.status-out", style: { "border-color": t.out, color: t.muted } },

    // ---------------------------------------------------------------- focus (clicking a node)
    { selector: "node.focused", style: { "underlay-color": t.accent, "underlay-opacity": 0.25, "underlay-padding": 6 } },
    { selector: "node.faded", style: { opacity: 0.12 } },
    { selector: "edge.faded", style: { opacity: EDGE_OPACITY.faded } },
    // Edge labels (heat thresholds) show for the clicked node's edges at any zoom.
    { selector: "edge.highlighted", style: { opacity: EDGE_OPACITY.highlighted, width: 1.5, "min-zoomed-font-size": 0 } },
    { selector: "edge.focused-edge", style: { width: 3, "line-color": t.accent, "target-arrow-color": t.accent } },
    { selector: "node:selected, edge:selected", style: { "overlay-opacity": 0 } },
  ];
}
