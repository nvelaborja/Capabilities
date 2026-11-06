import type { CollectionReturnValue, Core, NodeSingular } from "cytoscape";

/** Classes for edges and nodes that aren't showing: folded into a summary, or outside focus mode. */
export const FOLDED = "folded";
export const OUTSIDE = "outside";

/**
 * A node and everything one step away that is showing: what it needs, what it helps make, and the categories it
 * belongs to (or a category's members). This is "one level deep" (ADR 0020).
 */
export function neighbourhood(node: NodeSingular): CollectionReturnValue {
  const edges = node.connectedEdges().not(`.${FOLDED}, .${OUTSIDE}`);
  return node.union(edges).union(edges.connectedNodes());
}

/**
 * Focus mode: everything that could feed into the node, through every route and at every depth, plus what it
 * directly helps make. This is "what would it take?" (Q1) on the graph.
 */
export function lineage(node: NodeSingular): CollectionReturnValue {
  return node.union(node.predecessors()).union(node.outgoers());
}

/** Show only the node's lineage; null shows the whole graph again. */
export function isolate(cy: Core, id: string | null): void {
  cy.batch(() => {
    cy.elements().removeClass(OUTSIDE);
    const node = id ? cy.getElementById(id) : null;
    if (!node || node.empty()) return;
    cy.elements().not(lineage(node)).not(".level-label").addClass(OUTSIDE);
  });
}

const FOCUS_CLASSES = "faded focused highlighted";

/** Fade everything outside the node's neighbourhood and bring its edges forward. */
export function focusOn(node: NodeSingular): void {
  const cy = node.cy();
  const keep = neighbourhood(node);
  cy.batch(() => {
    cy.elements().removeClass(FOCUS_CLASSES);
    // Level headings stay visible so the columns still read while focused.
    cy.elements().not(keep).not(".level-label").addClass("faded");
    keep.edges().addClass("highlighted");
    node.addClass("focused");
  });
}

export function clearFocus(cy: Core): void {
  cy.batch(() => cy.elements().removeClass(FOCUS_CLASSES));
}
