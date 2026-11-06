import { type CSSProperties, useCallback, useRef, useState } from "react";

import { type Pane, type PaneSizes, readSizes, saveSizes, SIZE_VARIABLES } from "./sizes";

/** What the splitters and the app grid need; the grid element itself comes separately as a ref. */
export interface PaneLayout {
  /** Custom properties for the app grid. */
  style: CSSProperties;
  sizes: PaneSizes;
  /** The pane's size as drawn now, in pixels: the side column's width, or a pane's height. */
  measure: (pane: Pane) => number;
  /** Show a size while dragging without re-rendering the app on every pointer move. */
  preview: (pane: Pane, size: number) => void;
  /** Keep a size, or go back to the default with null. */
  commit: (pane: Pane, size: number | null) => void;
}

const PANE_ELEMENTS: Record<Pane, string> = { side: ".side-column", detail: ".detail-pane", selected: ".selection-pane" };

/**
 * Pane sizes the user has set. Attach `ref` to the app grid.
 *
 * The side and detail panes are remembered in this browser. The Selected pane's size holds only for the selection it
 * was set on (ADR 0030): any change to the selection, undo included, fits the pane to its chips again (up to half the
 * column). It is reset while rendering, React's pattern for state that follows a prop, not in an effect.
 */
export function usePaneSizes(selectionKey: string): { ref: React.RefObject<HTMLDivElement | null>; layout: PaneLayout } {
  const ref = useRef<HTMLDivElement | null>(null);
  const [saved, setSaved] = useState<PaneSizes>(readSizes);
  const [selected, setSelected] = useState<{ size: number; selection: string } | null>(null);
  // Forget it as soon as the selection changes, so undoing back to the same selection still fits the chips.
  if (selected && selected.selection !== selectionKey) setSelected(null);
  const sizes: PaneSizes = { ...saved };
  if (selected?.selection === selectionKey) sizes.selected = selected.size;

  const measure = useCallback((pane: Pane) => {
    const box = ref.current?.querySelector(PANE_ELEMENTS[pane])?.getBoundingClientRect();
    if (!box) return 0;
    return pane === "side" ? box.width : box.height;
  }, []);

  const preview = useCallback((pane: Pane, size: number) => {
    ref.current?.style.setProperty(SIZE_VARIABLES[pane], `${size}px`);
    // The Selected pane only follows its variable once sized (panes.css), so switch that on while dragging too.
    if (pane === "selected") ref.current?.classList.add("selected-sized");
  }, []);

  const commit = useCallback(
    (pane: Pane, size: number | null) => {
      if (size === null) ref.current?.style.removeProperty(SIZE_VARIABLES[pane]);
      if (pane === "selected") {
        if (size === null) ref.current?.classList.remove("selected-sized");
        setSelected(size === null ? null : { size, selection: selectionKey });
        return;
      }
      setSaved((previous) => {
        const next = { ...previous };
        if (size === null) delete next[pane];
        else next[pane] = size;
        saveSizes(next);
        return next;
      });
    },
    [selectionKey],
  );

  const style = Object.fromEntries(
    (Object.keys(sizes) as Pane[]).map((pane) => [SIZE_VARIABLES[pane], `${sizes[pane]}px`]),
  ) as CSSProperties;

  return { ref, layout: { style, sizes, measure, preview, commit } };
}
