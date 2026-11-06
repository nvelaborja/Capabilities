import { useEffect, useState } from "react";

export interface PostState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

/**
 * POST `body` shortly after it changes, cancelling any request in flight. `subject` names what the answer is about
 * (a node, a line): while the body changes for the same subject (the selection changed), the previous answer stays
 * up until the new one arrives, so the pane doesn't flicker; an answer about another subject is never shown.
 */
export function usePost<B, T>(call: (body: B, signal: AbortSignal) => Promise<T>, body: B | null, subject: string | null, delayMs = 100): PostState<T> {
  const key = body === null ? null : JSON.stringify(body);
  const [state, setState] = useState<{ data: T | null; error: string | null; key: string | null; subject: string | null }>({
    data: null,
    error: null,
    key: null,
    subject: null,
  });

  useEffect(() => {
    if (!key) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      call(JSON.parse(key) as B, controller.signal)
        .then((data) => setState({ data, error: null, key, subject }))
        .catch((error: unknown) => {
          if (!controller.signal.aborted) setState({ data: null, error: String(error), key, subject });
        });
    }, delayMs);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [call, key, subject, delayMs]);

  if (!key) return { data: null, loading: false, error: null };
  return {
    data: state.subject === subject ? state.data : null,
    loading: state.key !== key,
    error: state.key === key ? state.error : null,
  };
}
