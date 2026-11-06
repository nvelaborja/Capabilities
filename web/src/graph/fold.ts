import type { Core } from "cytoscape";

import { LIMIT } from "../lib/bounded";
import { FOLDED, OUTSIDE } from "./focus";

export interface HubNode {
  id: string;
  kind: string;
  label: string;
  level: number | null;
  prerequisites: number;
}

export interface HubEdge {
  id: string;
  source: string;
  target: string;
}

/** Highest tech level first, then the most certain prerequisites, then by name; no level last (ADR 0018). */
export function compareRank(a: HubNode, b: HubNode): number {
  const level = (node: HubNode) => (node.level === null ? -Infinity : node.level);
  return level(b) - level(a) || b.prerequisites - a.prerequisites || a.label.localeCompare(b.label);
}

/**
 * The lines a busy node doesn't draw (ADR 0030): a node linked to more than `limit` others in one direction keeps
 * lines to its `limit` most advanced neighbours, and the rest are hidden until the node, or the one at the other end,
 * is clicked. A line either end hides stays hidden. Nodes are never hidden, only lines.
 */
export function extraLines(nodes: readonly HubNode[], edges: readonly HubEdge[], limit = LIMIT): Set<string> {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const hidden = new Set<string>();
  for (const direction of ["out", "in"] as const) {
    const links = new Map<string, Map<string, string[]>>();
    for (const edge of edges) {
      const [hub, other] = direction === "out" ? [edge.source, edge.target] : [edge.target, edge.source];
      if (!byId.has(hub) || !byId.has(other)) continue;
      const neighbours = links.get(hub) ?? new Map<string, string[]>();
      neighbours.set(other, [...(neighbours.get(other) ?? []), edge.id]);
      links.set(hub, neighbours);
    }
    for (const neighbours of links.values()) {
      const ranked = [...neighbours.keys()].map((id) => byId.get(id) as HubNode).sort(compareRank);
      for (const extra of ranked.slice(limit)) {
        for (const edge of neighbours.get(extra.id) ?? []) hidden.add(edge);
      }
    }
  }
  return hidden;
}

/** Hide busy nodes' extra lines among what is showing, so focus mode bounds its own subgraph. */
export function applyFolding(cy: Core, limit = LIMIT): void {
  const showing = cy.nodes().not(`.level-label, .${OUTSIDE}`);
  const nodes: HubNode[] = showing.map((node) => ({
    id: node.id(),
    label: node.data("label") as string,
    kind: node.data("kind") as string,
    level: (node.data("level") as number | null) ?? null,
    prerequisites: (node.data("prerequisites") as number | undefined) ?? 0,
  }));
  const edges = cy
    .edges()
    .filter((edge) => !edge.hasClass(OUTSIDE))
    .map((edge) => ({ id: edge.id(), source: edge.data("source") as string, target: edge.data("target") as string }));
  const hidden = extraLines(nodes, edges, limit);
  cy.batch(() => {
    cy.edges().forEach((edge) => {
      edge.toggleClass(FOLDED, hidden.has(edge.id()));
    });
  });
}

/** Expand all: every line showing. */
export function unfoldAll(cy: Core): void {
  cy.batch(() => cy.edges().removeClass(FOLDED));
}
