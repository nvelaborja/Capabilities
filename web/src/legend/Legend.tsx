import { type CSSProperties, useState } from "react";

import type { DrawnKind, Status } from "../api/types";
import { STATUS_LOOK, TYPE_ICONS } from "../graph/styles";
import "./Legend.css";

// Drawn with the same CSS variables, emoji and border rules as the graph (graph/styles.ts).
export const TYPE_LABELS: Record<DrawnKind, string> = {
  material: "Material",
  artifact: "Tool or product",
  action: "Action (cut wood)",
  category: "Class (iron ore: any member will do)",
  effect: "Effect (heat)",
};

export const STATUS_LABELS: Record<Status, string> = {
  selected: "Selected",
  hypothetical: "What-if",
  implied: "Implied (required by the selection)",
  reachable: "Reachable (can be made or done from the selection)",
  maybe: "Maybe reachable",
  near: "One step away",
  out: "Out of reach",
};

/** A tiny node: the type's strip and emoji on the left, the status border around the whole thing. */
function MiniNode({ kind, status }: { kind: DrawnKind; status?: Status }) {
  const look = status ? STATUS_LOOK[status] : STATUS_LOOK.reachable;
  const colour = status === "out" ? "var(--out)" : `var(--type-${kind}-line)`;
  const dashes = look["border-dash-pattern"];
  const style: CSSProperties = dashes
    ? { opacity: look.opacity }
    : { borderWidth: look["border-width"], borderStyle: look["border-style"], borderColor: colour, opacity: look.opacity };
  return (
    <span className="mini-node" style={style} aria-hidden="true">
      <span className="mini-node-strip" style={{ background: `var(--type-${kind}-fill)` }}>
        {TYPE_ICONS[kind]}
      </span>
      {dashes && <DashedOutline width={look["border-width"]} dashes={dashes} colour={colour} />}
    </span>
  );
}

/**
 * CSS can't space out dashes, so a sparse dashed border is drawn in SVG to match the graph. The stroke is doubled
 * because the node clips its outer half.
 */
function DashedOutline({ width, dashes, colour }: { width: number; dashes: readonly [number, number]; colour: string }) {
  return (
    <svg className="mini-node-outline">
      <rect width="100%" height="100%" rx="5" fill="none" stroke={colour} strokeWidth={width * 2} strokeDasharray={dashes.join(" ")} />
    </svg>
  );
}

// A new key: the old one remembered "open", which was the default before the legend moved into the toolbar.
const OPEN_KEY = "capabilities.legend.shown";

// Hidden by default. Per-viewer convenience only: storage can be unavailable (private windows), so failures keep it hidden.
function readOpen(): boolean {
  try {
    return window.localStorage.getItem(OPEN_KEY) === "true";
  } catch {
    return false;
  }
}

function saveOpen(open: boolean): void {
  try {
    window.localStorage.setItem(OPEN_KEY, String(open));
  } catch {
    // Remembering the legend is optional.
  }
}

export function Legend() {
  const [open] = useState(readOpen);
  return (
    <details className="legend" open={open} onToggle={(event) => saveOpen(event.currentTarget.open)}>
      <summary>Legend</summary>
      <div className="legend-body">
        <section aria-label="Types">
          <h2>Strip: what it is</h2>
          <ul>
            {(Object.keys(TYPE_LABELS) as DrawnKind[]).map((kind) => (
              <li key={kind}>
                <MiniNode kind={kind} />
                {TYPE_LABELS[kind]}
              </li>
            ))}
          </ul>
        </section>
        <section aria-label="Statuses">
          <h2>Border: where it stands</h2>
          <ul>
            {(Object.keys(STATUS_LABELS) as Status[]).map((status) => (
              <li key={status}>
                <MiniNode kind="artifact" status={status} />
                {STATUS_LABELS[status]}
              </li>
            ))}
          </ul>
        </section>
        <p className="legend-note">
          Columns are tech levels: primitive things on the left, advanced ones on the right. Lines run from what a thing
          needs to the thing. Dashed lines are tools; dotted lines are actions. When there are several ways to make
          something, click it to see each one. Busy nodes draw lines only to their 8 most advanced neighbours; click one to
          see all its lines, or use Expand all. Click any line to see why it is there.
        </p>
      </div>
    </details>
  );
}
