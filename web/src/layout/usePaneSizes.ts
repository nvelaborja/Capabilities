import { type CSSProperties, useCallback, useRef, useState } from "react";

import { type Pane, type PaneSizes, readSizes, saveSizes, SIZE_VARIABLES } from "./sizes";

/** What the splitters and the app grid need; the grid element itself comes separately as a ref. */
export interface PaneLayout {
  /** Custom properties for the app grid. */
  style: CSSProperties;
  sizes: PaneSizes;
  /** The pane's size as drawn now, in pixels (the grid's last column or row). */
  measure: (pane: Pane) => number;
  /** Show a size while dragging without re-rendering the app on every pointer move. */
  preview: (pane: Pane, size: number) => void;
  /** Keep a size, or go back to the default with null. */
  commit: (pane: Pane, size: number | null) => void;
}

/** Pane sizes the user has set, remembered in this browser. Attach `ref` to the app grid. */
export function usePaneSizes(): { ref: React.RefObject<HTMLDivElement | null>; layout: PaneLayout } {
  const ref = useRef<HTMLDivElement | null>(null);
  const [sizes, setSizes] = useState<PaneSizes>(readSizes);

  const measure = useCallback((pane: Pane) => {
    const element = ref.current;
    if (!element) return 0;
    const style = getComputedStyle(element);
    const tracks = (pane === "side" ? style.gridTemplateColumns : style.gridTemplateRows).split(" ");
    return parseFloat(tracks.at(-1) ?? "0") || 0;
  }, []);

  const preview = useCallback((pane: Pane, size: number) => {
    ref.current?.style.setProperty(SIZE_VARIABLES[pane], `${size}px`);
  }, []);

  const commit = useCallback((pane: Pane, size: number | null) => {
    if (size === null) ref.current?.style.removeProperty(SIZE_VARIABLES[pane]);
    setSizes((previous) => {
      const next = { ...previous };
      if (size === null) delete next[pane];
      else next[pane] = size;
      saveSizes(next);
      return next;
    });
  }, []);

  const style = Object.fromEntries(
    (Object.keys(sizes) as Pane[]).map((pane) => [SIZE_VARIABLES[pane], `${sizes[pane]}px`]),
  ) as CSSProperties;

  return { ref, layout: { style, sizes, measure, preview, commit } };
}
