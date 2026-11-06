import type { CSSProperties } from "react";

import type { Status } from "../api/types";
import { STATUS_LOOK, TYPE_ICONS } from "../graph/styles";
import { STATUS_LABELS } from "../legend/Legend";
import "./chips.css";

// Know-how isn't drawn on the graph, so it has no type colour; it still gets an emoji.
export const CHIP_ICONS: Record<string, string> = { ...TYPE_ICONS, technique: "📖", summary: "…" };

export interface ChipProps {
  id: string;
  label: string;
  kind: string;
  status?: Status;
  /** Short visible text inside the chip, such as what a near miss is missing. */
  note?: string;
  /** Extra detail for the tooltip; the same information is always reachable by clicking (ADR 0019). */
  title?: string;
  onPick: (id: string) => void;
  onRemove?: (id: string) => void;
}

/** An item drawn like a graph node: emoji strip for the type, border for the status (ADR 0022, 0025). */
export function NodeChip({ id, label, kind, status, note, title, onPick, onRemove }: ChipProps) {
  const look = status ? STATUS_LOOK[status] : STATUS_LOOK.reachable;
  const style: CSSProperties = { borderWidth: look["border-width"], borderStyle: look["border-style"], opacity: look.opacity };
  const statusText = status ? ` (${STATUS_LABELS[status].toLowerCase()})` : "";
  return (
    <span className={`chip chip-${kind}${status ? ` chip-${status}` : ""}`} style={style}>
      <span className="chip-strip" aria-hidden="true">
        {CHIP_ICONS[kind] ?? "•"}
      </span>
      <button type="button" className="chip-label" onClick={() => onPick(id)} title={title} aria-label={`${label}${note ? `, ${note}` : ""}${statusText}`}>
        {label}
        {note && <span className="chip-note">{note}</span>}
      </button>
      {onRemove && (
        <button type="button" className="chip-remove" onClick={() => onRemove(id)} aria-label={`Remove ${label}`} title="Remove">
          ×
        </button>
      )}
    </span>
  );
}
