import { type ReactNode, useState } from "react";

import type { DrawnKind, Status } from "../api/types";
import { STATUS_LOOK } from "../graph/styles";
import "./Legend.css";

const W = 30;
const H = 18;

// Type colours, drawn with the same CSS variables the graph uses (graph/styles.ts).
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

// SVG dash patterns standing in for the graph's border styles.
const DASHES: Record<string, string | undefined> = { dotted: "1.5 2.5", dashed: "5 3" };

function Swatch({ children }: { children: ReactNode }) {
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-hidden="true" className="legend-swatch">
      {children}
    </svg>
  );
}

function TypeSwatch({ kind }: { kind: DrawnKind }) {
  return (
    <Swatch>
      <rect x={1.5} y={1.5} width={W - 3} height={H - 3} rx={5} fill={`var(--type-${kind}-tint)`} stroke={`var(--type-${kind}-line)`} />
    </Swatch>
  );
}

/** A status shown on a tool-coloured box, mirroring STATUS_LOOK. */
function StatusSwatch({ status }: { status: Status }) {
  const look = STATUS_LOOK[status];
  const width = look["border-width"];
  const strong = look.hadIt;
  const out = status === "out";
  const stroke = status === "selected" || status === "hypothetical" ? "var(--text)" : out ? "var(--out)" : "var(--type-artifact-line)";
  const fill = strong ? "var(--type-artifact-fill)" : out || status === "near" ? "var(--surface)" : "var(--type-artifact-tint)";
  const inset = Math.max(width, 1) / 2 + 0.5;
  return (
    <Swatch>
      <rect
        x={inset}
        y={inset}
        width={W - 2 * inset}
        height={H - 2 * inset}
        rx={5}
        fill={fill}
        stroke={width > 0 ? stroke : "none"}
        strokeWidth={look["border-style"] === "double" ? 1.5 : width}
        strokeDasharray={DASHES[look["border-style"]]}
        opacity={look.opacity}
      />
      {look["border-style"] === "double" && (
        <rect x={5} y={5} width={W - 10} height={H - 10} rx={3} fill="none" stroke={stroke} strokeWidth={1.5} />
      )}
    </Swatch>
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
          <h2>Colour: what it is</h2>
          <ul>
            {(Object.keys(TYPE_LABELS) as DrawnKind[]).map((kind) => (
              <li key={kind}>
                <TypeSwatch kind={kind} />
                {TYPE_LABELS[kind]}
              </li>
            ))}
            <li>
              <Swatch>
                <circle cx={W / 2} cy={H / 2} r={4} fill="var(--edge)" />
              </Swatch>
              A way to make it
            </li>
          </ul>
        </section>
        <section aria-label="Statuses">
          <h2>Border and fill: where it stands</h2>
          <ul>
            {(Object.keys(STATUS_LABELS) as Status[]).map((status) => (
              <li key={status}>
                <StatusSwatch status={status} />
                {STATUS_LABELS[status]}
              </li>
            ))}
          </ul>
        </section>
        <p className="legend-note">
          Columns are tech levels: primitive things on the left, advanced ones on the right. Several dots into a thing
          mean <em>any one</em> of these ways works. Lines into one dot mean that way needs <em>all</em> of them. Dashed
          lines are tools; dotted lines are actions.
        </p>
      </div>
    </details>
  );
}
