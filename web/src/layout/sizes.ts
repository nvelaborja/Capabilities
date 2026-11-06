/** The two panes the user can resize, by dragging or with the keyboard on the gap beside them (ADR 0028). */
export type Pane = "side" | "detail";

/** Sizes in pixels; a missing size follows the default in theme.css. */
export type PaneSizes = Partial<Record<Pane, number>>;

export interface Bounds {
  min: number;
  max: number;
}

export const STEP = 16;
export const BIG_STEP = 64;

/** The custom property each size sets on the app grid. */
export const SIZE_VARIABLES: Record<Pane, string> = { side: "--side-width", detail: "--detail-height" };

// The graph keeps at least this much room, so it can never be squeezed out of sight.
const GRAPH_MIN_WIDTH = 320;
const GRAPH_MIN_HEIGHT = 160;
const HEADER_ROOM = 80;

export function boundsFor(pane: Pane, viewport: { width: number; height: number }): Bounds {
  if (pane === "side") return { min: 240, max: Math.max(240, viewport.width - GRAPH_MIN_WIDTH) };
  return { min: 140, max: Math.max(140, viewport.height - HEADER_ROOM - GRAPH_MIN_HEIGHT) };
}

export function clampSize(size: number, bounds: Bounds): number {
  return Math.round(Math.min(bounds.max, Math.max(bounds.min, size)));
}

/**
 * The new size after a key press on a pane's splitter, or null if the key doesn't resize. The side pane is on the
 * right and the detail pane at the bottom, so moving the gap left or up makes them bigger.
 */
export function keyResize(pane: Pane, key: string, shift: boolean, size: number, bounds: Bounds): number | null {
  const step = shift ? BIG_STEP : STEP;
  const [grow, shrink] = pane === "side" ? ["ArrowLeft", "ArrowRight"] : ["ArrowUp", "ArrowDown"];
  if (key === grow) return clampSize(size + step, bounds);
  if (key === shrink) return clampSize(size - step, bounds);
  if (key === "Home") return bounds.min;
  if (key === "End") return bounds.max;
  return null;
}

/** The new size while dragging: the pane grows by however far the pointer moved towards the graph. */
export function dragResize(start: { pointer: number; size: number }, pointer: number, bounds: Bounds): number {
  return clampSize(start.size + (start.pointer - pointer), bounds);
}

const STORAGE_KEY = "capabilities.layout.sizes";

// Per-viewer convenience: storage can be unavailable (private windows), so failures fall back to the defaults.
export function readSizes(): PaneSizes {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "{}");
    if (typeof parsed !== "object" || parsed === null) return {};
    const sizes: PaneSizes = {};
    for (const pane of ["side", "detail"] as const) {
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
