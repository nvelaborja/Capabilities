import type { DrawnKind, ExploreResponse, Status } from "../api/types";
import type { Catalog } from "../catalog";
import { STATUS_LABELS, TYPE_LABELS } from "../legend/Legend";

interface NodeCardProps {
  id: string;
  catalog: Catalog;
  explore: ExploreResponse | null;
  onAdd: (id: string) => void;
  onRemove: (id: string) => void;
  onClose: () => void;
}

const SELECTABLE = new Set(["material", "artifact", "action"]);

/**
 * A small card for the clicked node, with the button that adds it to (or removes it from) the selection. The
 * detail pane (phase 4) grows out of this.
 */
export function NodeCard({ id, catalog, explore, onAdd, onRemove, onClose }: NodeCardProps) {
  const entry = catalog.get(id);
  const status = explore?.status[id] as Status | undefined;
  const explicit = explore ? [...explore.selected, ...explore.hypothetical].includes(id) : false;
  const neededBy = (explore?.implied_by[id] ?? []).map((source) => catalog.get(source).label.toLowerCase());
  const near = explore?.near.find((item) => item.id === id);
  const kindLabel = TYPE_LABELS[entry.kind as DrawnKind] ?? entry.kind;

  return (
    <section className="node-card" aria-label={`${entry.label} details`}>
      <header>
        <div>
          <h2>{entry.label}</h2>
          <p className="node-card-meta">
            {kindLabel}
            {status && ` · ${STATUS_LABELS[status]}`}
          </p>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close">
          ×
        </button>
      </header>
      {status === "implied" && neededBy.length > 0 && <p>They must have had this: it is needed by {neededBy.join(", ")}.</p>}
      {near && (
        <p>
          One step away: missing{" "}
          {[...new Set(near.routes.map((route) => route.missing.label.toLowerCase()))].join(" or ")}.
        </p>
      )}
      {entry.kind === "category" && <p>This stands for any of its members. Select a specific member instead.</p>}
      {entry.kind === "effect" && <p>Effects follow from what is selected; they can't be selected themselves.</p>}
      {SELECTABLE.has(entry.kind) && (
        <div className="node-card-actions">
          {explicit ? (
            <button type="button" onClick={() => onRemove(id)}>
              Remove from selected
            </button>
          ) : (
            <button type="button" className="primary" onClick={() => onAdd(id)}>
              Add to selected
            </button>
          )}
        </div>
      )}
    </section>
  );
}
