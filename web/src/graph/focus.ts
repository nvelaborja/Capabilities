import type { CollectionReturnValue, Core, NodeSingular } from "cytoscape";

/**
 * A node and everything one step away: what it needs, what it helps make, and the categories it belongs to (or a
 * category's members). This is "one level deep" (ADR 0020).
 */
export function neighbourhood(node: NodeSingular): CollectionReturnValue {
  return node.closedNeighborhood();
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
