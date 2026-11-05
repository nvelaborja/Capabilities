import { type ReactNode, useState } from "react";

import type { DrawnKind, Status } from "../api/types";
import "./Legend.css";

const W = 30;
const H = 18;

// Same shapes the graph uses (graph/styles.ts), drawn as small SVGs.
export const SHAPES: Record<DrawnKind | "route", { label: string; draw: (props: SwatchStyle) => ReactNode }> = {
  material: { label: "Material", draw: (s) => <ellipse cx={W / 2} cy={H / 2} rx={W / 2 - 2} ry={H / 2 - 2} {...s} /> },
  artifact: { label: "Tool or product", draw: (s) => <rect x={2} y={2} width={W - 4} height={H - 4} rx={4} {...s} /> },
  action: { label: "Action (cut wood)", draw: (s) => <polygon points="7,2 23,2 28,9 23,16 7,16 2,9" {...s} /> },
  category: { label: "Any of a kind (iron ore)", draw: (s) => <polygon points="15,1 28,9 15,17 2,9" {...s} /> },
  effect: { label: "Effect (heat)", draw: (s) => <polygon points="10,2 20,2 27,6 27,12 20,16 10,16 3,12 3,6" {...s} /> },
  route: { label: "A way to make it", draw: () => <circle cx={W / 2} cy={H / 2} r={4} fill="var(--edge)" /> },
};

interface SwatchStyle {
  fill: string;
  stroke: string;
  strokeWidth: number;
  strokeDasharray?: string;
  opacity?: number;
}

const NEUTRAL: SwatchStyle = { fill: "var(--surface)", stroke: "var(--text-muted)", strokeWidth: 1 };

// Mirrors the status rules in graph/styles.ts: fill or border pattern, never colour alone.
export const STATUS_STYLES: Record<Status, { label: string; style: SwatchStyle; double?: boolean }> = {
  selected: { label: "Selected", style: { fill: "var(--accent)", stroke: "var(--accent-strong)", strokeWidth: 3 } },
  hypothetical: { label: "What-if", style: { fill: "var(--what-if)", stroke: "var(--accent-strong)", strokeWidth: 1.5 }, double: true },
  implied: { label: "Implied (they must have had it)", style: { fill: "var(--accent-tint)", stroke: "var(--accent)", strokeWidth: 2 } },
  reachable: { label: "Reachable (they could have made it)", style: { fill: "var(--surface)", stroke: "var(--accent)", strokeWidth: 2 } },
  maybe: { label: "Maybe reachable", style: { fill: "var(--surface)", stroke: "var(--accent)", strokeWidth: 2, strokeDasharray: "1.5 2.5" } },
  near: { label: "One step away", style: { fill: "var(--surface)", stroke: "var(--text-muted)", strokeWidth: 2, strokeDasharray: "5 3" } },
  out: { label: "Out of reach", style: { fill: "var(--surface)", stroke: "var(--out)", strokeWidth: 1, opacity: 0.55 } },
};

function Swatch({ children }: { children: ReactNode }) {
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-hidden="true" className="legend-swatch">
      {children}
    </svg>
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
        <section aria-label="Shapes">
          <h2>Shape: what it is</h2>
          <ul>
            {Object.entries(SHAPES).map(([kind, { label, draw }]) => (
              <li key={kind}>
                <Swatch>{draw(NEUTRAL)}</Swatch>
                {label}
              </li>
            ))}
          </ul>
        </section>
        <section aria-label="Statuses">
          <h2>Fill and border: where it stands</h2>
          <ul>
            {Object.entries(STATUS_STYLES).map(([status, { label, style, double }]) => (
              <li key={status}>
                <Swatch>
                  <rect x={2} y={2} width={W - 4} height={H - 4} rx={4} {...style} />
                  {double && <rect x={5} y={5} width={W - 10} height={H - 10} rx={2} fill="none" stroke={style.stroke} strokeWidth={1.5} />}
                </Swatch>
                {label}
              </li>
            ))}
          </ul>
        </section>
        <p className="legend-note">
          Several dots into a thing mean <em>any one</em> of these ways works. Lines into one dot mean that way needs{" "}
          <em>all</em> of them. Dashed lines are tools; dotted lines are actions.
        </p>
      </div>
    </details>
  );
}
