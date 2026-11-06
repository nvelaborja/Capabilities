import type { RequirementRow, RouteRow } from "../api/types";
import { BoundedList } from "./BoundedList";
import { Mark } from "./Mark";
import { References } from "./References";
import { ROLE_TAGS, routeVerdict } from "./marks";

interface RoutesProps {
  routes: readonly RouteRow[];
  onDrill: (id: string) => void;
}

/**
 * Each way to get the node, with only its direct requirements (ADR 0020), missing ones first. Clicking a requirement
 * drills into it to see what *it* is missing.
 */
export function Routes({ routes, onDrill }: RoutesProps) {
  if (routes.length === 0) return <p className="muted">No known way to make it.</p>;
  return (
    <BoundedList
      className="routes"
      items={routes}
      kindOf={() => "route"}
      keyOf={(route) => route.id}
      render={(route) => <RouteItem route={route} open={routes.length <= 2 || route === routes[0]} onDrill={onDrill} />}
    />
  );
}

function RouteItem({ route, open, onDrill }: { route: RouteRow; open: boolean; onDrill: (id: string) => void }) {
  return (
    <li>
      <details className={`route route-${route.status}`} open={open}>
        <summary>
          <span className="route-label">{route.label}</span>
          <span className={`verdict verdict-${route.status}`}>{routeVerdict(route)}</span>
        </summary>
        <BoundedList
          className="requirements"
          items={route.requirements}
          kindOf={(row) => row.kind}
          keyOf={(row) => `${row.id}/${row.role}/${(row.conditions ?? []).join()}`}
          render={(row) => <RequirementItem row={row} onDrill={onDrill} />}
        />
        {route.provides && <p className="route-fact">Reaches: {route.provides.join(" · ")}</p>}
        {route.byproducts && <p className="route-fact">Also makes: {route.byproducts.map((b) => b.label.toLowerCase()).join(", ")}</p>}
        {route.techniques.length > 0 && <p className="route-fact">Know-how: {route.techniques.map((t) => t.label).join(", ")}</p>}
        <details className="route-sources">
          <summary>Sources ({route.references.length})</summary>
          <References references={route.references} />
        </details>
      </details>
    </li>
  );
}

function RequirementItem({ row, onDrill }: { row: RequirementRow; onDrill: (id: string) => void }) {
  const role = ROLE_TAGS[row.role];
  return (
    <li className={`requirement requirement-${row.status}`}>
      <Mark tri={row.status} />
      <span className="requirement-body">
        <button type="button" className="drill" onClick={() => onDrill(row.id)} title={`What does ${row.label.toLowerCase()} need?`}>
          {row.label}
          <span aria-hidden="true"> ›</span>
        </button>
        {role && <span className="role-tag">{role}</span>}
        {row.conditions && <span className="conditions">{row.conditions.join(" · ")}</span>}
        {row.reason && <span className="reason">{row.reason}</span>}
        {row.notes && (
          <details className="requirement-notes">
            <summary>Why</summary>
            {row.notes}
          </details>
        )}
      </span>
    </li>
  );
}
