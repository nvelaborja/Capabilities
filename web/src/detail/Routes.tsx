import type { RequirementRow, RouteRow, Status, Tri } from "../api/types";
import { NodeChip } from "../chips/NodeChip";
import { BoundedList } from "./BoundedList";
import { Mark } from "./Mark";
import { References } from "./References";
import { ROLE_TAGS, routeVerdict } from "./marks";

/** The status border for a requirement's chip: where the selection puts it. */
export type StatusOf = (id: string, tri: Tri) => Status;

interface RoutesProps {
  routes: readonly RouteRow[];
  statusOf: StatusOf;
  onDrill: (id: string) => void;
}

/**
 * Each way to get the node, with only its direct requirements (ADR 0020), missing ones first. Clicking a requirement
 * drills into it to see what *it* is missing.
 */
export function Routes({ routes, statusOf, onDrill }: RoutesProps) {
  if (routes.length === 0) return <p className="muted">No known way to make it.</p>;
  return (
    <BoundedList
      className="routes"
      items={routes}
      kindOf={() => "route"}
      keyOf={(route) => route.id}
      render={(route) => <RouteItem route={route} open={routes.length <= 2 || route === routes[0]} statusOf={statusOf} onDrill={onDrill} />}
    />
  );
}

function RouteItem({ route, open, statusOf, onDrill }: { route: RouteRow; open: boolean; statusOf: StatusOf; onDrill: (id: string) => void }) {
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
          render={(row) => <RequirementItem row={row} statusOf={statusOf} onDrill={onDrill} />}
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

/** One requirement: whether it is met (✓ ✗ ?), the item as a chip, its role and threshold, and why. */
interface RequirementItemProps {
  row: RequirementRow;
  statusOf: StatusOf;
  onDrill: (id: string) => void;
  /** Leave out the chip where the item is already named, such as under "From" when explaining a line. */
  showChip?: boolean;
}

export function RequirementItem({ row, statusOf, onDrill, showChip = true }: RequirementItemProps) {
  const role = ROLE_TAGS[row.role];
  return (
    <li className={`requirement requirement-${row.status}`}>
      <Mark tri={row.status} />
      <span className="requirement-body">
        {showChip && (
          <NodeChip id={row.id} label={row.label} kind={row.kind} status={statusOf(row.id, row.status)} onPick={onDrill} title={`What does ${row.label.toLowerCase()} need?`} />
        )}
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
