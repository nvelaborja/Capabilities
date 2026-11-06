import { type CSSProperties, useState } from "react";

import type { DrawnKind, Status } from "../api/types";
import { STATUS_LOOK, TYPE_ICONS } from "../graph/styles";
import "./Legend.css";

// Drawn with the same CSS variables, emoji and border rules as the graph (graph/styles.ts).
export const TYPE_LABELS: Record<DrawnKind, string> = {
  material: "Material",
  artifact: "Tool or product",
  action: "Action (cut wood)",
  category: "Any of a kind (iron ore)",
  effect: "Effect (heat)",
};

export const STATUS_LABELS: Record<Status, string> = {
  selected: "Selected",
  hypothetical: "What-if",
  implied: "Implied (they must have had it)",
  reachable: "Reachable (they could have made it)",
  maybe: "Maybe reachable",
  near: "One step away",
  out: "Out of reach",
};

/** A tiny node: the type's strip and emoji on the left, the status border around the whole thing. */
function MiniNode({ kind, status }: { kind: DrawnKind; status?: Status }) {
  const look = status ? STATUS_LOOK[status] : STATUS_LOOK.reachable;
  const style: CSSProperties = {
    borderWidth: look["border-width"],
    borderStyle: look["border-style"],
    borderColor: status === "out" ? "var(--out)" : `var(--type-${kind}-line)`,
    opacity: look.opacity,
  };
  return (
    <span className="mini-node" style={style} aria-hidden="true">
      <span className="mini-node-strip" style={{ background: `var(--type-${kind}-fill)` }}>
        {TYPE_ICONS[kind]}
      </span>
    </span>
  );
}

const OPEN_KEY = "capabilities.legend.open";

// Per-viewer convenience only: storage can be unavailable (private windows), so failures fall back to open.
function readOpen(): boolean {
  try {
    return window.localStorage.getItem(OPEN_KEY) !== "false";
  } catch {
    return true;
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
          something, click it to see each one.
        </p>
      </div>
    </details>
  );
}
