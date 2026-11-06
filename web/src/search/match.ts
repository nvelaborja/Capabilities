import type { GraphResponse } from "../api/types";

export interface SearchEntry {
  id: string;
  label: string;
  kind: string;
  /** Actions not on the graph yet are added to it when chosen. */
  drawn: boolean;
}

/** Every thing on the graph, plus every action the data allows ("Cut limestone"), drawn or not. */
export function searchIndex(graph: GraphResponse): SearchEntry[] {
  const entries = graph.nodes
    .filter((node) => node.kind !== "route")
    .map((node) => ({ id: node.id, label: node.label, kind: node.kind, drawn: true }));
  const drawn = new Set(entries.map((entry) => entry.id));
  for (const action of graph.actions) {
    if (!drawn.has(action.id)) entries.push({ id: action.id, label: action.label, kind: "action", drawn: false });
  }
  return entries;
}

const words = (text: string) => text.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter(Boolean);

/**
 * Entries whose words start with every word typed ("cut gra" finds "Cut granite"). Best first: an exact label, then
 * labels that start with the query, then shorter labels, then alphabetical.
 */
export function search(entries: readonly SearchEntry[], query: string, limit = 12): SearchEntry[] {
  const typed = words(query);
  if (typed.length === 0) return [];
  const whole = query.trim().toLowerCase();
  const score = (entry: SearchEntry) => {
    const label = entry.label.toLowerCase();
    return label === whole ? 0 : label.startsWith(whole) ? 1 : 2;
  };
  return entries
    .filter((entry) => {
      const have = words(entry.label);
      return typed.every((word) => have.some((candidate) => candidate.startsWith(word)));
    })
    .sort((a, b) => score(a) - score(b) || a.label.length - b.label.length || a.label.localeCompare(b.label))
    .slice(0, limit);
}
