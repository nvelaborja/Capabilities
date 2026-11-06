import type { Core } from "cytoscape";

import type { ExploreResponse, Status } from "../api/types";

export const STATUSES: readonly Status[] = ["selected", "hypothetical", "implied", "reachable", "maybe", "near", "out"];

const STATUS_CLASSES = STATUSES.map(statusClass).join(" ");

export function statusClass(status: Status): string {
  return `status-${status}`;
}

/**
 * Restyle nodes and edges for a new explore result without touching positions (ADR 0016: status changes never
 * re-run the layout). An edge is "live" when any route behind it works.
 */
export function applyStatuses(cy: Core, explore: ExploreResponse | null): void {
  cy.batch(() => {
    cy.elements().removeClass(`${STATUS_CLASSES} live`);
    if (!explore) return;
    cy.nodes().forEach((node) => {
      const status = explore.status[node.id()];
      if (status) node.addClass(statusClass(status));
    });
    cy.edges().forEach((edge) => {
      const routes = (edge.data("routes") as string[] | undefined) ?? [];
      if (routes.some((route) => explore.route_status[route] === "yes")) edge.addClass("live");
    });
  });
}
