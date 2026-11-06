/**
 * The detail pane's breadcrumb (Steel › Bloom iron › Iron ore). Opening a node starts a new trail; drilling into a
 * requirement extends it. It is navigation, not part of undo/redo, which covers only the selection (ADR 0020).
 */
export type Trail = readonly string[];

export type TrailAction =
  | { type: "open"; id: string }
  | { type: "drill"; id: string }
  | { type: "back"; index: number }
  | { type: "close" };

export function trailReducer(trail: Trail, action: TrailAction): Trail {
  switch (action.type) {
    case "open":
      return trail.length === 1 && trail[0] === action.id ? trail : [action.id];
    case "drill": {
      // Drilling back into something already on the trail returns to it rather than looping.
      const existing = trail.indexOf(action.id);
      return existing === -1 ? [...trail, action.id] : trail.slice(0, existing + 1);
    }
    case "back":
      return action.index >= 0 && action.index < trail.length - 1 ? trail.slice(0, action.index + 1) : trail;
    case "close":
      return trail.length === 0 ? trail : [];
  }
}

export function current(trail: Trail): string | null {
  return trail.at(-1) ?? null;
}
