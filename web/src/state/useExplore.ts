import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { ExploreResponse, SelectionRequest } from "../api/types";

export interface ExploreState {
  data: ExploreResponse | null;
  error: string | null;
}

/**
 * Explore results for a selection, recomputed shortly after every change (ADR 0016). A newer selection cancels
 * any request still in flight, so results never arrive out of order.
 */
export function useExplore(selection: SelectionRequest, delayMs = 150): ExploreState {
  const key = JSON.stringify(selection);
  const [state, setState] = useState<ExploreState>({ data: null, error: null });

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api
        .explore(JSON.parse(key) as SelectionRequest, controller.signal)
        .then((data) => setState({ data, error: null }))
        .catch((error: unknown) => {
          if (!controller.signal.aborted) {
            setState((previous) => ({ data: previous.data, error: String(error) }));
          }
        });
    }, delayMs);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [key, delayMs]);

  return state;
}
