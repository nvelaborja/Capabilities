import type { CSSProperties } from "react";

import { STATUS_LOOK, TYPE_ICONS } from "../graph/styles";
import { STATUS_LABELS } from "../legend/Legend";
import type { Chip } from "./groups";

// Know-how isn't drawn on the graph, so it has no type colour; it still gets an emoji.
const ICONS: Record<string, string> = { ...TYPE_ICONS, technique: "📖" };

interface NodeChipProps {
  chip: Chip;
  onPick: (id: string) => void;
  onRemove?: (id: string) => void;
}

/** A list item drawn like a graph node: emoji strip for the type, border for the status (ADR 0022, 0025). */
export function NodeChip({ chip, onPick, onRemove }: NodeChipProps) {
  const look = STATUS_LOOK[chip.status];
  const style: CSSProperties = { borderWidth: look["border-width"], borderStyle: look["border-style"], opacity: look.opacity };
  return (
    <li className={`chip chip-${chip.kind} chip-${chip.status}`} style={style}>
      <span className="chip-strip" aria-hidden="true">
        {ICONS[chip.kind] ?? "•"}
      </span>
      <button
        type="button"
        className="chip-label"
        onClick={() => onPick(chip.id)}
        title={chip.title}
        aria-label={`${chip.label}${chip.note ? `, ${chip.note}` : ""} (${STATUS_LABELS[chip.status].toLowerCase()})`}
      >
        {chip.label}
        {chip.note && <span className="chip-note">{chip.note}</span>}
      </button>
      {chip.removable && onRemove && (
        <button type="button" className="chip-remove" onClick={() => onRemove(chip.id)} aria-label={`Remove ${chip.label}`} title="Remove">
          ×
        </button>
      )}
    </li>
  );
}
