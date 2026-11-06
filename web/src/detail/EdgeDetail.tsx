import type { EdgeResponse, EdgeRoute, ItemRow } from "../api/types";
import { NodeChip } from "../chips/NodeChip";
import { STATUS_LABELS } from "../legend/Legend";
import { useExplainEdge } from "../state/useExplain";
import { DetailShell } from "./DetailShell";
import { lineStyle } from "./lines";
import { chipStatus, routeVerdict } from "./marks";
import type { DetailContext } from "./NodeDetail";
import { RequirementItem, Routes, type StatusOf } from "./Routes";

interface EdgeDetailProps extends DetailContext {
  source: string;
  target: string;
}

/**
 * Why a line joins two nodes, read left to right like the graph: where it starts and how that thing is used (From),
 * what the line's style and label mean and the routes behind it (Through), and where it ends (To).
 */
export function EdgeDetail(props: EdgeDetailProps) {
  const { source, target, catalog, explore, selection, crumbs, onBack, onDrill, onClose } = props;
  const { data, loading, error } = useExplainEdge(selection, { source, target });
  const statusOf: StatusOf = (id, tri) => chipStatus(explore?.status[id], tri);
  const from = catalog.get(source).label;
  const to = catalog.get(target).label;

  return (
    <DetailShell
      label={`${from} to ${to}`}
      crumbs={crumbs}
      onBack={onBack}
      onClose={onClose}
      title={
        <>
          {from} <span aria-label="to">→</span> {to}
        </>
      }
      meta={data && <span className="kind-chip">{data.kind === "is_a" ? "Is a kind of" : `Needed to make ${to.toLowerCase()}`}</span>}
    >
      {error && <p className="error">Couldn't explain this line.</p>}
      {!data && !error && loading && <p className="muted">Loading…</p>}
      {data && (
        <>
          <section className="detail-column" aria-labelledby="from-title">
            <h3 id="from-title">From</h3>
            <EndChip item={data.source} onDrill={onDrill} />
            {data.kind === "is_a" ? (
              <p>
                {data.source.label} is a kind of {data.target.label.toLowerCase()}.
              </p>
            ) : (
              <HowUsed routes={data.routes} statusOf={statusOf} onDrill={onDrill} />
            )}
          </section>
          <section className="detail-column" aria-labelledby="through-title">
            <h3 id="through-title">The line</h3>
            <Through data={data} statusOf={statusOf} onDrill={onDrill} />
          </section>
          <section className="detail-column" aria-labelledby="to-title">
            <h3 id="to-title">To</h3>
            <EndChip item={data.target} onDrill={onDrill} />
            <p className="muted">Click either end to see everything about it.</p>
          </section>
        </>
      )}
    </DetailShell>
  );
}

function EndChip({ item, onDrill }: { item: ItemRow; onDrill: (id: string) => void }) {
  return (
    <p className="edge-end">
      <NodeChip id={item.id} label={item.label} kind={item.kind} status={item.status} onPick={onDrill} />
      <span className="muted">{STATUS_LABELS[item.status]}</span>
    </p>
  );
}

/** For each route behind the line: the source's role, threshold, and whether it is met. */
function HowUsed({ routes, statusOf, onDrill }: { routes: EdgeRoute[]; statusOf: StatusOf; onDrill: (id: string) => void }) {
  return (
    <ul className="how-used">
      {routes.map((route) => (
        <li key={route.id}>
          <p className="how-used-route">
            In <strong>{route.label.toLowerCase()}</strong>
            {route.byproduct ? ", which makes it as a byproduct" : ""}:
          </p>
          <ul className="requirements">
            {route.link.map((row) => (
              <RequirementItem key={`${row.role}/${(row.conditions ?? []).join()}`} row={row} statusOf={statusOf} onDrill={onDrill} showChip={false} />
            ))}
          </ul>
        </li>
      ))}
    </ul>
  );
}

/** What the line's style, label and colour mean, then the routes behind it in full. */
function Through({ data, statusOf, onDrill }: { data: EdgeResponse; statusOf: StatusOf; onDrill: (id: string) => void }) {
  if (data.kind === "is_a") {
    const style = lineStyle("is_a", [], false);
    return (
      <>
        <p>
          <strong>{style.look}</strong>: {style.meaning}.
        </p>
        {data.used_by.length > 0 ? (
          <p>
            Routes that need any {data.target.label.toLowerCase()}: {data.used_by.join(", ")}.
          </p>
        ) : (
          <p className="muted">No route needs this kind directly.</p>
        )}
      </>
    );
  }
  const roles = data.routes.flatMap((route) => route.link.map((row) => row.role));
  const style = lineStyle("requires", roles, data.routes.every((route) => route.byproduct));
  const labelled = data.routes.some((route) => route.link.some((row) => row.conditions));
  const works = data.routes.some((route) => route.status === "yes");
  return (
    <>
      <p>
        <strong>{style.look}</strong>: {style.meaning}.
      </p>
      {labelled && (
        <p className="muted">
          The label on the line is the threshold each route needs{data.routes.length > 1 ? `; with ${data.routes.length} routes, they are joined by “or”` : ""}.
        </p>
      )}
      <p className="muted">
        {works
          ? "Drawn a little stronger: at least one of these routes works with the selection."
          : "Drawn faint: none of these routes works with the selection yet."}
      </p>
      <h4>
        {data.routes.length === 1 ? "The route" : `The ${data.routes.length} routes`} ({data.routes.map(routeVerdict).join(", ").toLowerCase()})
      </h4>
      <Routes routes={data.routes} statusOf={statusOf} onDrill={onDrill} />
    </>
  );
}
