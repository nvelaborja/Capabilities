/**
 * What the detail pane is showing. The breadcrumb trail holds plain strings, so lines and summary nodes get ids of
 * their own: "edge:heat|steel" and "summary:out:heat:material" (graph/summaries.ts).
 */
export type Subject =
  | { type: "node"; id: string }
  | { type: "edge"; source: string; target: string }
  | { type: "summary"; id: string };

const EDGE = "edge:";

export function edgeSubject(source: string, target: string): string {
  return `${EDGE}${source}|${target}`;
}

export function parseSubject(id: string): Subject {
  if (id.startsWith(EDGE)) {
    const [source = "", target = ""] = id.slice(EDGE.length).split("|");
    return { type: "edge", source, target };
  }
  if (id.startsWith("summary:")) return { type: "summary", id };
  return { type: "node", id };
}
