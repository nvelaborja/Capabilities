import { useEffect, useMemo, useRef, useState } from "react";

import type { SelectionRequest } from "../api/types";
import { NodeChip } from "../chips/NodeChip";
import { useExplain } from "../state/useExplain";
import type { StatusOf } from "./Routes";

interface ExpandAllDialogProps {
  node: string | null;
  label: string;
  selection: SelectionRequest;
  statusOf: StatusOf;
  onDrill: (id: string) => void;
  onClose: () => void;
}

const KIND_ORDER = ["source", "material", "artifact", "action", "category", "effect"];
const SECTIONS = [
  { key: "missing", title: "Missing" },
  { key: "uncertain", title: "Unknown" },
  { key: "have", title: "Have" },
] as const;

/** Everything a node certainly needs, at every depth, split into missing / unknown / have; each type on its own line. */
export function ExpandAllDialog({ node, label, selection, statusOf, onDrill, onClose }: ExpandAllDialogProps) {
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
                <ul key={group.kind} className="chip-row">
                  {group.rows.map((row) => (
                    <li key={row.id}>
                      <NodeChip
                        id={row.id}
                        label={row.label}
                        kind={row.kind}
                        status={statusOf(row.id, row.status)}
                        note={row.conditions?.join(", ")}
                        onPick={onDrill}
                      />
                    </li>
                  ))}
                </ul>
              ))}
            </section>
          ))}
      </div>
    </dialog>
  );
}
