import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { ExplainResponse, SelectionRequest } from "../api/types";

export interface ExplainState {
  /** Only ever the node asked for: a stale answer for another node is never shown. */
  data: ExplainResponse | null;
  loading: boolean;
  error: string | null;
}

/**
 * The detail pane's explanation of a node, refreshed when the node or the selection changes. A newer request cancels
 * the one in flight. While the selection changes, the previous answer for the same node stays up until the new one
 * arrives, so the pane doesn't flicker.
 */
export function useExplain(selection: SelectionRequest, node: string | null, everything = false, delayMs = 100): ExplainState {
  const key = node ? JSON.stringify({ ...selection, node, all: everything }) : null;
  const [state, setState] = useState<ExplainState & { key: string | null }>({ data: null, loading: false, error: null, key: null });

  useEffect(() => {
    if (!key) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api
        .explain(JSON.parse(key) as Parameters<typeof api.explain>[0], controller.signal)
        .then((data) => setState({ data, loading: false, error: null, key }))
        .catch((error: unknown) => {
          if (!controller.signal.aborted) setState({ data: null, loading: false, error: String(error), key });
        });
    }, delayMs);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [key, delayMs]);

  if (!node) return { data: null, loading: false, error: null };
  const data = state.data?.id === node ? state.data : null;
  return { data, loading: state.key !== key, error: state.key === key ? state.error : null };
}
