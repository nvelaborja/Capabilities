import { useState } from "react";

import type { About, ExplainResponse, ExploreResponse, SelectionRequest } from "../api/types";
import type { Catalog } from "../catalog";
import { CHIP_ICONS, NodeChip } from "../chips/NodeChip";
import { STATUS_LABELS } from "../legend/Legend";
import { useExplain } from "../state/useExplain";
import { DetailShell } from "./DetailShell";
import { ExpandAllDialog } from "./ExpandAllDialog";
import { ItemChips, type QuickAdd } from "./ItemChips";
import { chipStatus, kindName, statusTri, waysHeading } from "./marks";
import { References } from "./References";
import { Routes, type StatusOf } from "./Routes";

const SELECTABLE = new Set(["material", "artifact", "action"]);
const EXPANDABLE = new Set(["material", "artifact", "action"]);

export interface DetailContext {
  catalog: Catalog;
  explore: ExploreResponse | null;
  selection: SelectionRequest;
  crumbs: { id: string; label: string }[];
  onBack: (index: number) => void;
  onDrill: (id: string) => void;
  onClose: () => void;
}

interface NodeDetailProps extends DetailContext {
  id: string;
  isolated: string | null;
  onAdd: (id: string) => void;
  onRemove: (id: string) => void;
  onIsolate: (id: string | null) => void;
}

/**
 * Everything about one node: what it needs (left), what it is (middle), and what it leads to (right), like the graph.
 * Requirements drill down; the breadcrumb leads back.
 */
export function NodeDetail(props: NodeDetailProps) {
  const { id, catalog, explore, selection, crumbs, isolated, onBack, onDrill, onClose, onAdd, onRemove, onIsolate } = props;
  const { data, loading, error } = useExplain(selection, id);
  const [expanding, setExpanding] = useState<string | null>(null);

  const entry = catalog.get(id);
  const status = explore?.status[id] ?? data?.status;
  const chosen = new Set(explore ? [...explore.selected, ...explore.hypothetical] : []);
  const explicit = chosen.has(id);
  const quickAdd: QuickAdd = { isChosen: (member) => chosen.has(member), onAdd };
  const impliedBy = (explore?.implied_by[id] ?? []).map((source) => catalog.get(source).label.toLowerCase());
  const statusOf: StatusOf = (other, tri) => chipStatus(explore?.status[other], tri);
  const icon = CHIP_ICONS[entry.kind];
  // "Move anything" stands for the verb on every target: it isn't drawn and can't be selected as such.
  const anyTarget = id.endsWith(":(any)");
  const onGraph = entry.kind !== "technique" && !anyTarget;

  return (
    <DetailShell
      label={entry.label}
      crumbs={crumbs}
      onBack={onBack}
      onClose={onClose}
      title={entry.label}
      meta={
        <>
          <span className={`kind-chip kind-${entry.kind}`}>
            {icon && <span aria-hidden="true">{icon} </span>}
            {kindName(entry.kind)}
          </span>
          {data?.level !== undefined && data.level !== null && <span>Level {data.level}</span>}
          {status && <span className={`status-chip status-chip-${statusTri(status)}`}>{STATUS_LABELS[status]}</span>}
          {data?.about.era === "modern" && <span className="modern-chip">Modern, for comparison</span>}
        </>
      }
      actions={
        <>
          {SELECTABLE.has(entry.kind) &&
            !anyTarget &&
            (explicit ? (
              <button type="button" onClick={() => onRemove(id)}>
                Remove from selected
              </button>
            ) : (
              <button type="button" className="primary" onClick={() => onAdd(id)}>
                Add to selected
              </button>
            ))}
          {onGraph && (
            <button type="button" aria-pressed={isolated === id} onClick={() => onIsolate(isolated === id ? null : id)}>
              {isolated === id ? "Show whole graph" : "Focus"}
            </button>
          )}
        </>
      }
    >
      {error && <p className="error">Couldn't load the details.</p>}
      {!data && !error && loading && <p className="muted">Loading…</p>}
      {data && (
        <>
          <section className="detail-column" aria-labelledby="needs-title">
            <Needs
              data={data}
              statusOf={statusOf}
              onDrill={onDrill}
              quickAdd={quickAdd}
              onExpandAll={canExpand(data) ? () => setExpanding(id) : undefined}
            />
          </section>
          <section className="detail-column" aria-labelledby="about-title">
            <h3 id="about-title">About</h3>
            {status === "implied" && impliedBy.length > 0 && (
              <p className="detail-note">Required by the selection: {impliedBy.join(", ")} needs it.</p>
            )}
            {entry.kind === "category" && (
              <p className="detail-note">A class stands for any one of its members, so it can't be selected itself. Add a member instead.</p>
            )}
            {entry.kind === "effect" && <p className="detail-note">Effects follow from what is selected, so they can't be selected themselves.</p>}
            {entry.kind === "technique" && (
              <p className="detail-note">Know-how describes how something was done. It never decides whether it could be done.</p>
            )}
            <AboutSection about={data.about} statusOf={statusOf} onDrill={onDrill} />
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
              <ItemChips items={data.leads_to} onDrill={onDrill} />
            )}
          </section>
        </>
      )}
      <ExpandAllDialog
        node={expanding === id ? id : null}
        label={entry.label}
        selection={selection}
        statusOf={statusOf}
        onDrill={(next) => {
          setExpanding(null);
          onDrill(next);
        }}
        onClose={() => setExpanding(null)}
      />
    </DetailShell>
  );
}

const canExpand = (data: ExplainResponse) => EXPANDABLE.has(data.kind) && (data.routes?.length ?? 0) > 0;

interface NeedsProps {
  data: ExplainResponse;
  statusOf: StatusOf;
  onDrill: (id: string) => void;
  /** For a class: add a member to the selection in one click. */
  quickAdd: QuickAdd;
  onExpandAll?: () => void;
}

/** The left column: what it takes to get this (or, for know-how, where it is used). */
function Needs({ data, statusOf, onDrill, quickAdd, onExpandAll }: NeedsProps) {
  if (data.members) {
    return (
      <>
        <h3 id="needs-title">Class members</h3>
        <ItemChips items={data.members} onDrill={onDrill} quickAdd={quickAdd} />
      </>
    );
  }
  if (data.used_in) {
    return (
      <>
        <h3 id="needs-title">Used in</h3>
        <ul className="used-in">
          {data.used_in.map((route) => (
            <li key={route.id}>
              <span className="route-label">{route.label}</span>
              {route.makes.length > 0 ? (
                <span className="used-in-makes">
                  makes{" "}
                  {route.makes.map((item) => (
                    <NodeChip key={item.id} id={item.id} label={item.label} kind={item.kind} status={item.status} onPick={onDrill} />
                  ))}
                </span>
              ) : (
                <span className="used-in-makes">Nothing it makes is on the graph yet; search can add its actions.</span>
              )}
            </li>
          ))}
        </ul>
      </>
    );
  }
  const natural = data.about.origin === "natural" && (data.routes?.length ?? 0) === 0;
  return (
    <>
      <h3 id="needs-title">{waysHeading(data.kind)}</h3>
      {natural ? (
        <p className="muted">A natural material: gathered, not made.</p>
      ) : (
        <Routes routes={data.routes ?? []} statusOf={statusOf} onDrill={onDrill} />
      )}
      {onExpandAll && (
        <button type="button" className="expand-all" onClick={onExpandAll}>
          Expand all dependencies
        </button>
      )}
    </>
  );
}

function AboutSection({ about, statusOf, onDrill }: { about: About; statusOf: StatusOf; onDrill: (id: string) => void }) {
  const facts: [string, string][] = (about.quantities ?? []).map((q) => [q.label, q.value]);
  const natural = about.origin === "natural";
  const everywhere = about.availability === "ubiquitous";
  if (natural) facts.push(["Found", everywhere ? "Almost everywhere" : (about.regions ?? []).join("; ") || "Some regions"]);
  return (
    <div className="about">
      {about.description && <p className="description">{about.description}</p>}
      {about.target && (
        <p>
          Acting on{" "}
          <NodeChip id={about.target.id} label={about.target.label} kind="material" status={statusOf(about.target.id, "no")} onPick={onDrill} />
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
      {natural && (
        <p className="detail-note">
          {everywhere
            ? "Always available: found almost everywhere, so every selection has it."
            : "Not assumed: found only in some regions, so add it, or select something that needs it."}
        </p>
      )}
      {about.member_of && about.member_of.length > 0 && (
        <p className="member-of">
          Member of{" "}
          {about.member_of.map((category) => (
            <NodeChip key={category.id} id={category.id} label={category.label} kind="category" status={statusOf(category.id, "no")} onPick={onDrill} />
          ))}
        </p>
      )}
      {about.notes && <p className="muted">{about.notes}</p>}
    </div>
  );
}
