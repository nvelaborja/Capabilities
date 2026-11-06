import { useEffect, useMemo, useRef, useState } from "react";

import type { DependencyRow, SelectionRequest } from "../api/types";
import { useExplain } from "../state/useExplain";
import { Mark } from "./Mark";
import { kindName } from "./marks";

interface ExpandAllDialogProps {
  node: string | null;
  label: string;
  selection: SelectionRequest;
  onDrill: (id: string) => void;
  onClose: () => void;
}

const KIND_ORDER = ["material", "artifact", "action", "category", "effect"];
const SECTIONS = [
  { key: "missing", title: "Missing" },
  { key: "uncertain", title: "Unknown" },
  { key: "have", title: "Have" },
] as const;

/** Everything a node certainly needs, at every depth, split into missing / unknown / have and grouped by type. */
export function ExpandAllDialog({ node, label, selection, onDrill, onClose }: ExpandAllDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const [filter, setFilter] = useState("");
  const { data, loading, error } = useExplain(selection, node, true);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (node && !dialog.open) dialog.showModal();
    if (!node && dialog.open) dialog.close();
  }, [node]);

  const all = data?.all;
  const query = filter.trim().toLowerCase();
  const sections = useMemo(
    () =>
      SECTIONS.map((section) => {
        const rows = (all?.[section.key] ?? []).filter((row) => row.label.toLowerCase().includes(query));
        const groups = KIND_ORDER.map((kind) => ({ kind, rows: rows.filter((row) => row.kind === kind) })).filter((g) => g.rows.length > 0);
        return { ...section, count: rows.length, groups };
      }),
    [all, query],
  );

  return (
    <dialog
      ref={ref}
      className="expand-dialog"
      aria-labelledby="expand-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <header>
        <h2 id="expand-title">Everything {label.toLowerCase()} needs</h2>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close">
          ×
        </button>
      </header>
      <p className="muted">What it certainly needs at every depth, whichever way it is made.</p>
      <input
        type="search"
        className="filter"
        placeholder="Filter"
        aria-label="Filter dependencies"
        value={filter}
        onChange={(event) => setFilter(event.target.value)}
      />
      <div className="expand-body">
        {loading && !all && <p className="muted">Working it out…</p>}
        {error && <p className="error">Couldn't load the full list.</p>}
        {all &&
          sections.map((section) => (
            <section key={section.key} aria-label={section.title}>
              <h3>
                {section.title} <span className="count">{section.count}</span>
              </h3>
              {section.count === 0 && <p className="muted">None.</p>}
              {section.groups.map((group) => (
                <div key={group.kind} className="expand-group">
                  <h4>{kindName(group.kind, group.rows.length)}</h4>
                  <ul>
                    {group.rows.map((row) => (
                      <DependencyItem key={row.id} row={row} onDrill={onDrill} />
                    ))}
                  </ul>
                </div>
              ))}
            </section>
          ))}
      </div>
    </dialog>
  );
}

function DependencyItem({ row, onDrill }: { row: DependencyRow; onDrill: (id: string) => void }) {
  return (
    <li className="dependency">
      <Mark tri={row.status} />
      <button type="button" className="drill" onClick={() => onDrill(row.id)}>
        {row.label}
      </button>
      {row.conditions && <span className="conditions">{row.conditions.join(" · ")}</span>}
    </li>
  );
}
