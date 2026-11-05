import type { Core, EdgeSingular, NodeCollection } from "cytoscape";
import type dagre from "cytoscape-dagre";

/** Below this zoom, node labels are too small to read, so the first view zooms in to it instead of fitting all. */
export const READABLE_ZOOM = 0.8;
const PADDING = 24;

/**
 * The shortest an edge may be, in layout columns. Tech levels give each node a column (see layoutRank); asking
 * dagre for at least that gap pulls the drawing into tech-level columns, primitives on the left. Edges that run
 * backwards (cycles, such as heat that burns charcoal made with heat) fall back to the minimum.
 */
export function minimumLength(sourceRank: number | null, targetRank: number | null): number {
  if (sourceRank === null || targetRank === null) return 1;
  return Math.max(1, targetRank - sourceRank);
}

export const LAYOUT: dagre.DagreLayoutOptions = {
  name: "dagre",
  rankDir: "LR",
  nodeSep: 14,
  rankSep: 56,
  edgeSep: 6,
  padding: PADDING,
  animate: false,
  fit: false,
  minLen: (edge: EdgeSingular) =>
    minimumLength(edge.source().data("rank") as number | null, edge.target().data("rank") as number | null),
};

/** Lay out everything except "is a" links, which would pull categories out of their columns. */
export function runLayout(cy: Core): void {
  cy.elements().not("edge.is_a").layout(LAYOUT).run();
}

/** Fit the graph if its labels stay readable; otherwise zoom to a readable size around what matters most. */
export function showInitialView(cy: Core, focus?: NodeCollection): void {
  cy.fit(undefined, PADDING);
  if (cy.zoom() >= READABLE_ZOOM) return;
  const target = focus && focus.nonempty() ? focus : cy.nodes();
  cy.zoom(READABLE_ZOOM);
  cy.center(target);
}
