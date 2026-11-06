import type { ElementDefinition } from "cytoscape";

import type { GraphNode, GraphResponse, RequirementRole } from "../api/types";

// Approximate width of one character at the node font size, so boxes fit their labels without measuring text.
const CHAR_WIDTH = 7;
const MIN_WIDTH = 56;
const MAX_WIDTH = 168;
/** Width of the coloured type strip on the left of every node (graph/styles.ts draws it). */
export const STRIP_WIDTH = 26;

export interface NodeSize {
  width: number;
  height: number;
}

/** Sized to the label (wrapping past MAX_WIDTH), plus the type strip. */
export function nodeSize(node: GraphNode): NodeSize {
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

/**
 * A drawn edge: an ingredient straight to something it helps make. Route junctions aren't drawn (ADR 0023); when
 * several routes link the same pair, they merge into one edge that remembers them all.
 */
export interface DrawnEdge {
  id: string;
  source: string;
  target: string;
  kind: "requires" | "is_a";
  /** The requirement roles behind this edge (consumed, tool, action, effect). */
  roles: RequirementRole[];
  /** Threshold labels such as "Temperature ≥ 1100 °C", one per distinct condition. */
  labels: string[];
  routes: string[];
  /** True only if every link behind the edge leads to a byproduct (slag). */
  byproduct: boolean;
}

/** Replace route junctions with direct edges from each requirement to each thing or action the route makes. */
export function drawnEdges(graph: GraphResponse): DrawnEdge[] {
  const products = new Map<string, { target: string; byproduct: boolean }[]>();
  for (const edge of graph.edges) {
    if (edge.kind === "produces" || edge.kind === "performs") {
      products.set(edge.source, [...(products.get(edge.source) ?? []), { target: edge.target, byproduct: edge.byproduct ?? false }]);
    }
  }
  const merged = new Map<string, DrawnEdge>();
  for (const edge of graph.edges) {
    if (edge.kind === "is_a") {
      merged.set(edge.id, { id: edge.id, source: edge.source, target: edge.target, kind: "is_a", roles: [], labels: [], routes: [], byproduct: false });
      continue;
    }
    if (edge.kind !== "requires") continue;
    for (const product of products.get(edge.target) ?? []) {
      if (product.target === edge.source) continue;
      const id = `${edge.source}->${product.target}`;
      const existing = merged.get(id) ?? {
        id, source: edge.source, target: product.target, kind: "requires" as const, roles: [], labels: [], routes: [], byproduct: true,
      };
      if (edge.role && !existing.roles.includes(edge.role)) existing.roles.push(edge.role);
      if (edge.label && !existing.labels.includes(edge.label)) existing.labels.push(edge.label);
      if (!existing.routes.includes(edge.target)) existing.routes.push(edge.target);
      existing.byproduct &&= product.byproduct;
      merged.set(id, existing);
    }
  }
  return [...merged.values()];
}

export function edgeClasses(edge: DrawnEdge): string[] {
  const classes: string[] = [edge.kind];
  // One role gives the line its style; an edge merged from different roles stays solid.
  if (edge.roles.length === 1) classes.push(`role-${edge.roles[0]}`);
  if (edge.kind === "requires" && edge.byproduct) classes.push("byproduct");
  return classes;
}

/** The layout column for a node: its tech level (ADR 0018), or null when unknown. */
export function layoutRank(node: GraphNode): number | null {
  return node.level ?? null;
}

/** The API graph as Cytoscape elements, without route junctions. Statuses are applied separately. */
export function toElements(graph: GraphResponse): ElementDefinition[] {
  const nodes: ElementDefinition[] = graph.nodes
    .filter((node) => node.kind !== "route")
    .map((node) => ({
      group: "nodes",
      data: { id: node.id, label: node.label, kind: node.kind, level: node.level ?? null, rank: layoutRank(node), ...nodeSize(node) },
      classes: nodeClasses(node),
    }));
  const edges: ElementDefinition[] = drawnEdges(graph).map((edge) => ({
    group: "edges",
    data: { id: edge.id, source: edge.source, target: edge.target, label: edge.labels.join(" or "), routes: edge.routes },
    classes: edgeClasses(edge),
  }));
  return [...nodes, ...edges];
}
