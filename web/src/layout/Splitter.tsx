import { type KeyboardEvent, type PointerEvent, useRef, useState } from "react";

import "./layout.css";
import { boundsFor, type Bounds, dragResize, keyResize, type Pane } from "./sizes";
import type { PaneLayout } from "./usePaneSizes";

const LABELS: Record<Pane, string> = {
  side: "Resize the side panes",
  detail: "Resize the detail pane",
  selected: "Resize the Selected pane",
};

const viewport = () => ({ width: window.innerWidth, height: window.innerHeight });

/**
 * The gap beside a pane: drag it, or focus it and use the arrow keys, Home and End, to resize the pane (ADR 0028).
 * Double-click puts the pane back to its default size.
 */
export function Splitter({ pane, layout }: { pane: Pane; layout: PaneLayout }) {
  const drag = useRef<{ pointer: number; size: number; bounds: Bounds; last: number } | null>(null);
  const [dragging, setDragging] = useState(false);
  const vertical = pane === "side";
  const position = (event: PointerEvent) => (vertical ? event.clientX : event.clientY);
  const bounds = boundsFor(pane, viewport());
  const size = layout.sizes[pane];

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    const start = layout.measure(pane);
    drag.current = { pointer: position(event), size: start, bounds: boundsFor(pane, viewport()), last: start };
    setDragging(true);
  };
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const current = drag.current;
    if (!current) return;
    current.last = dragResize(pane, current, position(event), current.bounds);
    layout.preview(pane, current.last);
  };
  const onPointerEnd = () => {
    const current = drag.current;
    if (!current) return;
    drag.current = null;
    setDragging(false);
    if (current.last !== current.size) layout.commit(pane, current.last);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const next = keyResize(pane, event.key, event.shiftKey, layout.measure(pane), bounds);
    if (next === null) return;
    event.preventDefault();
    layout.commit(pane, next);
  };

  return (
    <div
      role="separator"
      tabIndex={0}
      aria-label={LABELS[pane]}
      aria-orientation={vertical ? "vertical" : "horizontal"}
      aria-valuemin={bounds.min}
      aria-valuemax={bounds.max}
      aria-valuenow={size}
      title="Drag to resize. Double-click to reset."
      className={`splitter splitter-${vertical ? "vertical" : "horizontal"} splitter-${pane}${dragging ? " dragging" : ""}`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerEnd}
      onPointerCancel={onPointerEnd}
      onKeyDown={onKeyDown}
      onDoubleClick={() => layout.commit(pane, null)}
    />
  );
}
