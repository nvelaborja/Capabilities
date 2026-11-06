import { api } from "../api/client";
import type { EdgeRequest, EdgeResponse, ExplainRequest, ExplainResponse, SelectionRequest } from "../api/types";
import { type PostState, usePost } from "./usePost";

const explain = (body: ExplainRequest, signal: AbortSignal) => api.explain(body, signal);
const explainEdge = (body: EdgeRequest, signal: AbortSignal) => api.explainEdge(body, signal);

/** The detail pane's explanation of a node, refreshed when the node or the selection changes. */
export function useExplain(selection: SelectionRequest, node: string | null, everything = false): PostState<ExplainResponse> {
  const subject = node ? `${node}${everything ? "+all" : ""}` : null;
  return usePost(explain, node ? { ...selection, node, all: everything } : null, subject);
}

/** Why a line joins two nodes, refreshed when the selection changes. */
export function useExplainEdge(selection: SelectionRequest, line: { source: string; target: string } | null): PostState<EdgeResponse> {
  return usePost(explainEdge, line ? { ...selection, ...line } : null, line ? `${line.source}->${line.target}` : null);
}
