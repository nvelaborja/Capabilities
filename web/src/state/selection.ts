import type { ProfileItem, SelectionRequest } from "../api/types";

/**
 * What the user has chosen: a preset plus their own additions and removals (ADR 0017). Items are thing ids
 * ("copper-saw") or actions ("cut:granite"). This maps directly onto the explore request and the shareable link.
 */
export interface Selection {
  preset: string | null;
  added: string[];
  removed: string[];
}

export const EMPTY: Selection = { preset: null, added: [], removed: [] };

/** `inPreset` says whether the item is part of the current preset, so edits stay minimal. */
export type Edit =
  | { type: "add"; item: string; inPreset: boolean }
  | { type: "remove"; item: string; inPreset: boolean }
  | { type: "loadPreset"; preset: string | null }
  | { type: "clear" };

export type HistoryAction = Edit | { type: "undo" } | { type: "redo" };

export interface History {
  past: Selection[];
  present: Selection;
  future: Selection[];
}

export const HISTORY_LIMIT = 100;

const without = (items: string[], item: string) => items.filter((existing) => existing !== item);
const withItem = (items: string[], item: string) => (items.includes(item) ? items : [...items, item].sort());

export function applyEdit(selection: Selection, edit: Edit): Selection {
  switch (edit.type) {
    case "add":
      return edit.inPreset
        ? { ...selection, removed: without(selection.removed, edit.item) }
        : { ...selection, added: withItem(selection.added, edit.item), removed: without(selection.removed, edit.item) };
    case "remove":
      return edit.inPreset
        ? { ...selection, added: without(selection.added, edit.item), removed: withItem(selection.removed, edit.item) }
        : { ...selection, added: without(selection.added, edit.item) };
    case "loadPreset":
      return { preset: edit.preset, added: [], removed: [] };
    case "clear":
      return EMPTY;
  }
}

function sameSelection(a: Selection, b: Selection): boolean {
  return a.preset === b.preset && a.added.join() === b.added.join() && a.removed.join() === b.removed.join();
}

/** Every edit is one undoable step; edits that change nothing add no step. */
export function historyReducer(history: History, action: HistoryAction): History {
  if (action.type === "undo") {
    const previous = history.past.at(-1);
    if (!previous) return history;
    return { past: history.past.slice(0, -1), present: previous, future: [history.present, ...history.future] };
  }
  if (action.type === "redo") {
    const [next, ...rest] = history.future;
    if (!next) return history;
    return { past: [...history.past, history.present], present: next, future: rest };
  }
  const present = applyEdit(history.present, action);
  if (sameSelection(present, history.present)) return history;
  return { past: [...history.past, history.present].slice(-HISTORY_LIMIT), present, future: [] };
}

export function startHistory(present: Selection): History {
  return { past: [], present, future: [] };
}

/** Edited since the preset was loaded: switching presets would lose these changes, so we confirm first. */
export function isEdited(selection: Selection): boolean {
  return selection.added.length > 0 || selection.removed.length > 0;
}

export function toRequest(selection: Selection): SelectionRequest {
  return { profile: selection.preset, select: selection.added, deselect: selection.removed };
}

export function profileItemId(item: ProfileItem): string | null {
  if (item.id) return item.id;
  if (item.verb && item.target) return `${item.verb}:${item.target}`;
  return null;
}
