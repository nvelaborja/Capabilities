import { useEffect, useReducer } from "react";

import { historyReducer, startHistory } from "./selection";
import { historyShortcut } from "./shortcuts";
import { decodeSelection, encodeSelection } from "./url";

/**
 * The selection with undo/redo, starting from the link and keeping the link up to date. The link is replaced, not
 * pushed, so the browser's back button isn't flooded with edits; undo/redo is the history (ADR 0017).
 */
export function useSelectionHistory() {
  const [history, dispatch] = useReducer(historyReducer, undefined, () => startHistory(decodeSelection(window.location.search)));

  useEffect(() => {
    const { pathname, hash } = window.location;
    window.history.replaceState(null, "", `${pathname}${encodeSelection(history.present)}${hash}`);
  }, [history.present]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const step = historyShortcut(event);
      if (!step) return;
      event.preventDefault();
      dispatch({ type: step });
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return {
    selection: history.present,
    canUndo: history.past.length > 0,
    canRedo: history.future.length > 0,
    dispatch,
  };
}
