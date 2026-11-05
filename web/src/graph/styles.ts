import type { StylesheetJson } from "cytoscape";

/** Colours the graph needs, read from CSS custom properties so light and dark themes stay in one place (theme.css). */
export interface GraphTokens {
  surface: string;
  text: string;
  muted: string;
  border: string;
  accent: string;
  accentStrong: string;
  accentTint: string;
  onAccent: string;
  whatIf: string;
  edge: string;
  edgeLive: string;
  out: string;
}

const TOKEN_VARIABLES: Record<keyof GraphTokens, string> = {
  surface: "--surface",
  text: "--text",
  muted: "--text-muted",
  border: "--border",
  accent: "--accent",
  accentStrong: "--accent-strong",
  accentTint: "--accent-tint",
  onAccent: "--on-accent",
  whatIf: "--what-if",
  edge: "--edge",
  edgeLive: "--edge-live",
  out: "--out",
};

export function readTokens(root: Element = document.documentElement): GraphTokens {
  const computed = getComputedStyle(root);
  const entries = Object.entries(TOKEN_VARIABLES).map(([key, variable]) => [key, computed.getPropertyValue(variable).trim()]);
  return Object.fromEntries(entries) as GraphTokens;
}

const FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';

/**
 * Shape encodes the type of node and fill or border encodes its status, so status never depends on colour alone
 * (design doc, "Status styling"). Later rules override earlier ones.
 */
export function buildStylesheet(t: GraphTokens): StylesheetJson {
  return [
    // ---------------------------------------------------------------- base
    {
      selector: "node",
      style: {
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
        "border-color": t.border,
        "border-style": "solid",
        "min-zoomed-font-size": 7,
      },
    },
    { selector: "node.material", style: { shape: "ellipse" } },
    { selector: "node.artifact", style: { shape: "round-rectangle" } },
    { selector: "node.action", style: { shape: "hexagon" } },
    { selector: "node.category", style: { shape: "diamond", "font-style": "italic" } },
    { selector: "node.effect", style: { shape: "octagon" } },
    { selector: "node.ubiquitous", style: { "font-size": 11 } },
    {
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
        // Quiet by default so the routes that work (live edges) stand out.
        opacity: 0.55,
      },
    },
    { selector: "edge.role-tool", style: { "line-style": "dashed" } },
    { selector: "edge.role-action", style: { "line-style": "dotted" } },
    { selector: "edge.byproduct", style: { "line-style": "dotted" } },
    { selector: "edge.is_a", style: { width: 0.75, "line-style": "dashed", "target-arrow-shape": "none", opacity: 0.6 } },
    { selector: "edge.live", style: { "line-color": t.edgeLive, "target-arrow-color": t.edgeLive, width: 1.5, opacity: 0.9 } },

    // ---------------------------------------------------------------- statuses (fill or border, never colour alone)
    {
      selector: "node.status-selected",
      style: { "background-color": t.accent, color: t.onAccent, "border-width": 3, "border-color": t.accentStrong },
    },
    {
      selector: "node.status-hypothetical",
      style: { "background-color": t.whatIf, color: t.onAccent, "border-width": 4, "border-style": "double", "border-color": t.accentStrong },
    },
    { selector: "node.status-implied", style: { "background-color": t.accentTint, "border-width": 2, "border-color": t.accent } },
    { selector: "node.status-reachable", style: { "border-width": 2, "border-color": t.accent } },
    { selector: "node.status-maybe", style: { "border-width": 2, "border-style": "dotted", "border-color": t.accent } },
    { selector: "node.status-near", style: { "border-width": 2, "border-style": "dashed", "border-color": t.muted } },
    { selector: "node.status-out", style: { color: t.muted, "border-color": t.out, opacity: 0.55 } },
    { selector: "node.route.route-yes", style: { "background-color": t.accent } },
    { selector: "node.route.route-maybe", style: { "background-color": t.surface, "border-width": 1.5, "border-color": t.accent } },
    { selector: "node.route.route-no", style: { "background-color": t.out } },

    // ---------------------------------------------------------------- focus (clicking a node)
    { selector: "node.focused", style: { "underlay-color": t.accent, "underlay-opacity": 0.25, "underlay-padding": 6 } },
    { selector: ".faded", style: { opacity: 0.12 } },
    { selector: "node:selected", style: { "overlay-opacity": 0 } },
  ];
}
