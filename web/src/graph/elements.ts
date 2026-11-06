import type { ElementDefinition } from "cytoscape";

import type { GraphEdge, GraphNode, GraphResponse } from "../api/types";

// Approximate width of one character at the node font size, so boxes fit their labels without measuring text.
const CHAR_WIDTH = 7;
const MIN_WIDTH = 56;
const MAX_WIDTH = 168;
const ROUTE_SIZE = 10;
/** Width of the coloured type strip on the left of every node (graph/styles.ts draws it). */
export const STRIP_WIDTH = 24;

export interface NodeSize {
  width: number;
  height: number;
}

/** Route junctions are small dots; everything else is sized to its label (wrapping past MAX_WIDTH) plus the strip. */
export function nodeSize(node: GraphNode): NodeSize {
  if (node.kind === "route") {
    return { width: ROUTE_SIZE, height: ROUTE_SIZE };
  }
  const textWidth = node.label.length * CHAR_WIDTH + 20;
  const width = Math.round(Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, textWidth)));
  const lines = Math.ceil(textWidth / MAX_WIDTH);
  const base = isUbiquitous(node) ? 24 : 30;
  return { width: width + STRIP_WIDTH, height: base + (lines - 1) * 13 };
}

export function isUbiquitous(node: GraphNode): boolean {
  return node.kind === "material" && node.origin === "natural" && node.availability === "ubiquitous";
}

export function nodeClasses(node: GraphNode): string[] {
  const classes: string[] = [node.kind];
  if (isUbiquitous(node)) classes.push("ubiquitous");
  if (node.era === "modern") classes.push("modern");
  if (node.selectable) classes.push("selectable");
  return classes;
}

export function edgeClasses(edge: GraphEdge): string[] {
  const classes: string[] = [edge.kind];
  if (edge.role) classes.push(`role-${edge.role}`);
  if (edge.byproduct) classes.push("byproduct");
  return classes;
}

/**
 * The layout column for a node: things sit at twice their tech level and a route one column right of its highest
 * requirement, so a product lands one column right of the route that makes it (ADR 0018). Null when unknown.
 */
export function layoutRank(node: GraphNode): number | null {
  if (node.level === null || node.level === undefined) return null;
  return node.kind === "route" ? 2 * node.level + 1 : 2 * node.level;
}

/** The API graph as Cytoscape elements. Classes carry type and role; statuses are applied separately. */
export function toElements(graph: GraphResponse): ElementDefinition[] {
  const nodes: ElementDefinition[] = graph.nodes.map((node) => ({
    group: "nodes",
    data: { id: node.id, label: node.label, kind: node.kind, level: node.level ?? null, rank: layoutRank(node), ...nodeSize(node) },
    classes: nodeClasses(node),
  }));
  const edges: ElementDefinition[] = graph.edges.map((edge) => ({
    group: "edges",
    data: { id: edge.id, source: edge.source, target: edge.target, label: edge.label ?? "" },
    classes: edgeClasses(edge),
  }));
  return [...nodes, ...edges];
}
