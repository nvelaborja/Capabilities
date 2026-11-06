import { bound, LIMIT, summaryLabel } from "../lib/bounded";

export interface HubNode {
  id: string;
  label: string;
  kind: string;
  level: number | null;
  prerequisites: number;
}

export interface HubEdge {
  id: string;
  source: string;
  target: string;
}

/** One summary node: the edges from a hub to the neighbours beyond the first N, for one kind ("8 other materials"). */
export interface Summary {
  id: string;
  hub: string;
  /** "out": what the hub helps make; "in": what the hub needs. */
  direction: "in" | "out";
  kind: string;
  label: string;
  members: string[];
  edges: string[];
}

/** Highest tech level first, then the most certain prerequisites, then by name; no level last (ADR 0018). */
export function compareRank(a: HubNode, b: HubNode): number {
  const level = (node: HubNode) => (node.level === null ? -Infinity : node.level);
  return level(b) - level(a) || b.prerequisites - a.prerequisites || a.label.localeCompare(b.label);
}

/**
 * Bound every node's neighbourhood (ADR 0020, 0024): a node linked to more than `limit` others in one direction keeps
 * edges to the top `limit`, and the rest fold into one summary per kind. Nodes are never hidden: each still has its
 * place in its column (ADR 0023); only the hub's extra edges are folded away.
 */
export function summarise(nodes: readonly HubNode[], edges: readonly HubEdge[], limit = LIMIT): Summary[] {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const summaries: Summary[] = [];
  for (const direction of ["out", "in"] as const) {
    const links = new Map<string, Map<string, string[]>>();
    for (const edge of edges) {
      const [hub, other] = direction === "out" ? [edge.source, edge.target] : [edge.target, edge.source];
      if (!byId.has(hub) || !byId.has(other)) continue;
      const neighbours = links.get(hub) ?? new Map<string, string[]>();
      neighbours.set(other, [...(neighbours.get(other) ?? []), edge.id]);
      links.set(hub, neighbours);
    }
    for (const [hub, neighbours] of links) {
      const ranked = [...neighbours.keys()].map((id) => byId.get(id) as HubNode).sort(compareRank);
      for (const group of bound(ranked, (node) => node.kind, limit).hidden) {
        const members = group.items.map((node) => node.id);
        summaries.push({
          id: `summary:${direction}:${hub}:${group.kind}`,
          hub,
          direction,
          kind: group.kind,
          label: summaryLabel(group.kind, members.length),
          members,
          edges: members.flatMap((member) => neighbours.get(member) ?? []),
        });
      }
    }
  }
  return summaries;
}

/** Edges folded into a summary that hasn't been expanded. An edge two hubs both fold stays hidden until both expand. */
export function foldedEdges(summaries: readonly Summary[], expanded: ReadonlySet<string>): Set<string> {
  return new Set(summaries.filter((summary) => !expanded.has(summary.id)).flatMap((summary) => summary.edges));
}
