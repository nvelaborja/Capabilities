/** The panes the user can resize, by dragging or with the keyboard on the gap beside them (ADR 0028, 0029). */
export type Pane = "side" | "detail" | "selected";

// The Selected pane is left out: it fits each new selection again (ADR 0030), so its size isn't worth keeping.
const REMEMBERED: readonly Pane[] = ["side", "detail"];

/** Sizes in pixels; a missing size follows the default in theme.css. */
export type PaneSizes = Partial<Record<Pane, number>>;

export interface Bounds {
  min: number;
  max: number;
}

export const STEP = 16;
export const BIG_STEP = 64;

/** The custom property each size sets on the app grid. */
export const SIZE_VARIABLES: Record<Pane, string> = { side: "--side-width", detail: "--detail-height", selected: "--selected-height" };

/**
 * Which way the pointer moves to make a pane bigger: the side pane is on the right and the detail pane at the bottom,
 * so they grow as their gap moves left or up; the Selected pane is on top, so it grows as its gap moves down.
 */
const GROWS_WITH_POINTER: Record<Pane, 1 | -1> = { side: -1, detail: -1, selected: 1 };

const KEYS: Record<Pane, { grow: string; shrink: string }> = {
  side: { grow: "ArrowLeft", shrink: "ArrowRight" },
  detail: { grow: "ArrowUp", shrink: "ArrowDown" },
  selected: { grow: "ArrowDown", shrink: "ArrowUp" },
};

// The graph keeps at least this much room, so it can never be squeezed out of sight.
const GRAPH_MIN_WIDTH = 320;
const GRAPH_MIN_HEIGHT = 160;
const HEADER_ROOM = 80;
// The Implied and reachable pane keeps room for its header and a row of chips.
const REACH_MIN_HEIGHT = 140;

export function boundsFor(pane: Pane, viewport: { width: number; height: number }): Bounds {
  if (pane === "side") return { min: 240, max: Math.max(240, viewport.width - GRAPH_MIN_WIDTH) };
  if (pane === "selected") return { min: 72, max: Math.max(72, viewport.height - HEADER_ROOM - REACH_MIN_HEIGHT) };
  return { min: 140, max: Math.max(140, viewport.height - HEADER_ROOM - GRAPH_MIN_HEIGHT) };
}

export function clampSize(size: number, bounds: Bounds): number {
  return Math.round(Math.min(bounds.max, Math.max(bounds.min, size)));
}

/** The new size after a key press on a pane's splitter, or null if the key doesn't resize. Arrows move the gap. */
export function keyResize(pane: Pane, key: string, shift: boolean, size: number, bounds: Bounds): number | null {
  const step = shift ? BIG_STEP : STEP;
  if (key === KEYS[pane].grow) return clampSize(size + step, bounds);
  if (key === KEYS[pane].shrink) return clampSize(size - step, bounds);
  if (key === "Home") return bounds.min;
  if (key === "End") return bounds.max;
  return null;
}

/** The new size while dragging: the pane grows or shrinks by however far the gap moved. */
export function dragResize(pane: Pane, start: { pointer: number; size: number }, pointer: number, bounds: Bounds): number {
  return clampSize(start.size + GROWS_WITH_POINTER[pane] * (pointer - start.pointer), bounds);
}

const STORAGE_KEY = "capabilities.layout.sizes";

// Per-viewer convenience: storage can be unavailable (private windows), so failures fall back to the defaults.
export function readSizes(): PaneSizes {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "{}");
    if (typeof parsed !== "object" || parsed === null) return {};
    const sizes: PaneSizes = {};
    for (const pane of REMEMBERED) {
      const value = (parsed as Record<string, unknown>)[pane];
      if (typeof value === "number" && Number.isFinite(value) && value > 0) sizes[pane] = value;
    }
    return sizes;
  } catch {
    return {};
  }
}

export function saveSizes(sizes: PaneSizes): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(sizes));
  } catch {
    // Remembering sizes is optional.
  }
}
