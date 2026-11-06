import type { CollectionReturnValue, Core, EdgeSingular, NodeSingular } from "cytoscape";

/** Classes for lines and nodes that aren't showing: a busy node's extra lines (ADR 0030), or outside focus mode. */
export const FOLDED = "folded";
export const OUTSIDE = "outside";
/** A folded line drawn anyway, because one of its ends (or the line itself) is clicked. */
export const REVEALED = "revealed";

/**
 * A node and everything one step away that is showing: what it needs, what it helps make, and the categories it
 * belongs to (or a category's members). This is "one level deep" (ADR 0020). A busy node's extra lines count too,
 * since clicking it draws them.
 */
export function neighbourhood(node: NodeSingular): CollectionReturnValue {
  const edges = node.connectedEdges().not(`.${OUTSIDE}`);
  return node.union(edges).union(edges.connectedNodes());
}

/**
 * Focus mode (ADR 0030): the node, what it certainly needs at every depth (`needs`, from the API), and what it directly
 * helps make, with the lines between them. This is "what would it take?" (Q1) on the graph.
 */
export function lineage(node: NodeSingular, needs: readonly string[]): CollectionReturnValue {
  const cy = node.cy();
  let nodes = node.union(node.outgoers().nodes());
  for (const id of needs) nodes = nodes.union(cy.getElementById(id));
  const lines = nodes.connectedEdges().filter((edge) => nodes.contains(edge.source()) && nodes.contains(edge.target()));
  return nodes.union(lines);
}

/** Show only the node's lineage and hide everything else; null shows the whole graph again. */
export function isolate(cy: Core, id: string | null, needs: readonly string[] = []): void {
  cy.batch(() => {
    cy.elements().removeClass(OUTSIDE);
    const node = id ? cy.getElementById(id) : null;
    if (!node || node.empty()) return;
    cy.elements().not(lineage(node, needs)).not(".level-label").addClass(OUTSIDE);
  });
}

const FOCUS_CLASSES = `faded focused highlighted focused-edge ${REVEALED}`;

/** Fade everything outside the node's neighbourhood, draw all its lines, and bring them forward. */
export function focusOn(node: NodeSingular): void {
  const cy = node.cy();
  const keep = neighbourhood(node);
  cy.batch(() => {
    cy.elements().removeClass(FOCUS_CLASSES);
    keep.edges(`.${FOLDED}`).addClass(REVEALED);
    // Level headings stay visible so the columns still read while focused.
    cy.elements().not(keep).not(".level-label").addClass("faded");
    keep.edges().addClass("highlighted");
    node.addClass("focused");
  });
}

/** A clicked line: it and its two ends stand out, everything else fades. */
export function focusOnEdge(edge: EdgeSingular): void {
  const cy = edge.cy();
  const keep = edge.union(edge.connectedNodes());
  cy.batch(() => {
    cy.elements().removeClass(FOCUS_CLASSES);
    cy.elements().not(keep).not(".level-label").addClass("faded");
    edge.addClass(`highlighted focused-edge ${REVEALED}`);
    edge.connectedNodes().addClass("focused");
  });
}

/** The drawn line from one node to another, if there is one. */
export function findEdge(cy: Core, source: string, target: string): EdgeSingular | null {
  const edge = cy.getElementById(source).edgesTo(cy.getElementById(target)).first();
  return edge.nonempty() ? edge : null;
}

export function clearFocus(cy: Core): void {
  cy.batch(() => cy.elements().removeClass(FOCUS_CLASSES));
}
