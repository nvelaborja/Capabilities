import type { ReactNode } from "react";

import type { Group, Row } from "./groups";
import { countRows } from "./groups";

interface CapabilityListProps {
  id: string;
  title: string;
  groups: Group[];
  emptyText: string;
  onPick: (id: string) => void;
  onRemove?: (id: string) => void;
  headerAction?: ReactNode;
  children?: ReactNode;
}

function RowItem({ row, onPick, onRemove }: { row: Row; onPick: (id: string) => void; onRemove?: (id: string) => void }) {
  return (
    <li className="row">
      <button type="button" className="row-label" onClick={() => onPick(row.id)} title={`Show ${row.label} on the graph`}>
        {row.label}
      </button>
      {row.badge && <span className={`badge badge-${row.badge}`}>{row.badge === "implied" ? "implied" : "maybe"}</span>}
      {row.removable && onRemove && (
        <button type="button" className="row-remove" onClick={() => onRemove(row.id)} aria-label={`Remove ${row.label}`} title="Remove">
          ×
        </button>
      )}
      {row.note && <span className="row-note">{row.note}</span>}
    </li>
  );
}

/** One half of the right-hand pane: a titled, independently scrolling list of grouped rows. */
export function CapabilityList({ id, title, groups, emptyText, onPick, onRemove, headerAction, children }: CapabilityListProps) {
  return (
    <section className="capability-list" aria-labelledby={`${id}-title`}>
      <header className="capability-header">
        <h2 id={`${id}-title`}>
          {title} <span className="count">{countRows(groups)}</span>
        </h2>
        {headerAction}
      </header>
      <div className="capability-scroll">
        {groups.length === 0 && !children && <p className="empty">{emptyText}</p>}
        {groups.map((group) => (
          <details key={group.key} open className="group">
            <summary>
              {group.title} <span className="count">{group.rows.length}</span>
            </summary>
            <ul>
              {group.rows.map((row) => (
                <RowItem key={row.id} row={row} onPick={onPick} onRemove={onRemove} />
              ))}
            </ul>
          </details>
        ))}
        {children}
      </div>
    </section>
  );
}
