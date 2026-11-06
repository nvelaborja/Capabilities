import { useState } from "react";

import type { About, ExplainResponse, ExploreResponse, ItemRow, LeadsToRow, SelectionRequest } from "../api/types";
import type { Catalog } from "../catalog";
import { TYPE_ICONS } from "../graph/styles";
import { STATUS_LABELS } from "../legend/Legend";
import { current, type Trail } from "../state/trail";
import { useExplain } from "../state/useExplain";
import { BoundedList } from "./BoundedList";
import "./detail.css";
import { ExpandAllDialog } from "./ExpandAllDialog";
import { Mark } from "./Mark";
import { kindName, statusTri, waysHeading } from "./marks";
import { References } from "./References";
import { Routes } from "./Routes";

const SELECTABLE = new Set(["material", "artifact", "action"]);
const EXPANDABLE = new Set(["material", "artifact", "action"]);

interface DetailPaneProps {
  trail: Trail;
  catalog: Catalog;
  explore: ExploreResponse | null;
  selection: SelectionRequest;
  isolated: string | null;
  onDrill: (id: string) => void;
  onBack: (index: number) => void;
  onClose: () => void;
  onAdd: (id: string) => void;
  onRemove: (id: string) => void;
  onIsolate: (id: string | null) => void;
}

/**
 * Everything about one node (design doc, detail pane): what it is, each way to get it with its direct requirements,
 * what it leads to, and the sources. Requirements drill down; the breadcrumb leads back.
 */
export function DetailPane(props: DetailPaneProps) {
  const { trail, catalog, explore, selection, isolated, onDrill, onBack, onClose, onAdd, onRemove, onIsolate } = props;
  const id = current(trail);
  const { data, loading, error } = useExplain(selection, id);
  const [expanding, setExpanding] = useState<string | null>(null);
  if (!id) return null;

  const entry = catalog.get(id);
  const status = explore?.status[id];
  const explicit = explore ? [...explore.selected, ...explore.hypothetical].includes(id) : false;
  const impliedBy = (explore?.implied_by[id] ?? []).map((source) => catalog.get(source).label.toLowerCase());
  const icon = TYPE_ICONS[entry.kind as keyof typeof TYPE_ICONS];
  const level = data?.level;

  return (
    <section className="detail-pane" aria-label={`${entry.label} details`}>
      <header className="detail-bar">
        <div className="detail-title">
          {trail.length > 1 && (
            <nav className="breadcrumb" aria-label="Drill-down trail">
              <ol>
                {trail.slice(0, -1).map((crumb, index) => (
                  <li key={crumb}>
                    <button type="button" className="link-button" onClick={() => onBack(index)}>
                      {catalog.get(crumb).label}
                    </button>
                  </li>
                ))}
              </ol>
            </nav>
          )}
          <h2>{entry.label}</h2>
          <p className="detail-meta">
            <span className={`kind-chip kind-${entry.kind}`}>
              {icon && <span aria-hidden="true">{icon} </span>}
              {kindName(entry.kind)}
            </span>
            {level !== undefined && level !== null && <span>Level {level}</span>}
            {status && <span className={`status-chip status-chip-${statusTri(status)}`}>{STATUS_LABELS[status]}</span>}
            {data?.about.era === "modern" && <span className="modern-chip">Modern, for comparison</span>}
          </p>
        </div>
        <div className="detail-actions">
          {SELECTABLE.has(entry.kind) &&
            (explicit ? (
              <button type="button" onClick={() => onRemove(id)}>
                Remove from selected
              </button>
            ) : (
              <button type="button" className="primary" onClick={() => onAdd(id)}>
                Add to selected
              </button>
            ))}
          <button type="button" aria-pressed={isolated === id} onClick={() => onIsolate(isolated === id ? null : id)}>
            {isolated === id ? "Show whole graph" : "Focus"}
          </button>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close details" title="Close (Esc)">
            ×
          </button>
        </div>
      </header>

      {/* Left to right, like the graph: what it needs, what it is, what it leads to. */}
      <div className="detail-columns" key={id}>
        {error && <p className="error">Couldn't load the details.</p>}
        {!data && !error && loading && <p className="muted">Loading…</p>}
        {data && (
          <>
            <section className="detail-column" aria-labelledby="needs-title">
              <Needs data={data} onDrill={onDrill} onExpandAll={canExpand(data) ? () => setExpanding(id) : undefined} />
            </section>
            <section className="detail-column" aria-labelledby="about-title">
              <h3 id="about-title">About</h3>
              {status === "implied" && impliedBy.length > 0 && (
                <p className="detail-note">They must have had this: it is needed by {impliedBy.join(", ")}.</p>
              )}
              {entry.kind === "category" && <p className="detail-note">Stands for any of its members; select a specific member instead.</p>}
              {entry.kind === "effect" && <p className="detail-note">Effects follow from what is selected, so they can't be selected themselves.</p>}
              <AboutSection about={data.about} onDrill={onDrill} />
              {data.about.references.length > 0 && (
                <>
                  <h4>Sources</h4>
                  <References references={data.about.references} />
                </>
              )}
            </section>
            <section className="detail-column" aria-labelledby="leads-title">
              <h3 id="leads-title">Leads to</h3>
              {data.leads_to.length === 0 ? (
                <p className="muted">Nothing on the graph uses it directly.</p>
              ) : (
                <ItemList items={data.leads_to} onDrill={onDrill} />
              )}
            </section>
          </>
        )}
      </div>
      <ExpandAllDialog
        node={expanding === id ? id : null}
        label={entry.label}
        selection={selection}
        onDrill={(next) => {
          setExpanding(null);
          onDrill(next);
        }}
        onClose={() => setExpanding(null)}
      />
    </section>
  );
}

const canExpand = (data: ExplainResponse) => EXPANDABLE.has(data.kind) && (data.routes?.length ?? 0) > 0;

/** The left column: what it takes to get this. */
function Needs({ data, onDrill, onExpandAll }: { data: ExplainResponse; onDrill: (id: string) => void; onExpandAll?: () => void }) {
  if (data.members) {
    return (
      <>
        <h3 id="needs-title">Any of these would do</h3>
        <ItemList items={data.members} onDrill={onDrill} />
      </>
    );
  }
  const natural = data.about.origin === "natural" && (data.routes?.length ?? 0) === 0;
  return (
    <>
      <h3 id="needs-title">{waysHeading(data.kind)}</h3>
      {natural ? <p className="muted">A natural material: gathered, not made.</p> : <Routes routes={data.routes ?? []} onDrill={onDrill} />}
      {onExpandAll && (
        <button type="button" className="expand-all" onClick={onExpandAll}>
          Expand all dependencies
        </button>
      )}
    </>
  );
}

function AboutSection({ about, onDrill }: { about: About; onDrill: (id: string) => void }) {
  const facts: [string, string][] = (about.quantities ?? []).map((q) => [q.label, q.value]);
  if (about.origin === "natural") {
    const where = about.availability === "ubiquitous" ? "Found almost everywhere" : (about.regions ?? []).join("; ") || "Some regions";
    facts.push(["Found", where]);
  }
  return (
    <div className="about">
      {about.description && <p className="description">{about.description}</p>}
      {about.target && (
        <p>
          Acting on{" "}
          <button type="button" className="drill" onClick={() => onDrill(about.target?.id ?? "")}>
            {about.target.label}
          </button>
        </p>
      )}
      {facts.length > 0 && (
        <dl className="facts">
          {facts.map(([term, value]) => (
            <div key={term}>
              <dt>{term}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      )}
      {about.member_of && about.member_of.length > 0 && (
        <p className="member-of">
          A kind of{" "}
          {about.member_of.map((category, index) => (
            <span key={category.id}>
              {index > 0 && ", "}
              <button type="button" className="drill" onClick={() => onDrill(category.id)}>
                {category.label.toLowerCase()}
              </button>
            </span>
          ))}
        </p>
      )}
      {about.notes && <p className="muted">{about.notes}</p>}
    </div>
  );
}

function ItemList({ items, onDrill }: { items: readonly (ItemRow | LeadsToRow)[]; onDrill: (id: string) => void }) {
  return (
    <BoundedList
      className="items"
      items={items}
      kindOf={(item) => item.kind}
      keyOf={(item) => item.id}
      render={(item) => (
        <li className="item">
          <Mark tri={statusTri(item.status)} />
          <button type="button" className="drill" onClick={() => onDrill(item.id)}>
            {item.label}
          </button>
          {"via" in item && <span className="via">via {item.via.join(" or ").toLowerCase()}</span>}
        </li>
      )}
    />
  );
}
