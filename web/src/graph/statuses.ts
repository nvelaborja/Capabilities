import type { Core } from "cytoscape";

import type { ExploreResponse, Status, Tri } from "../api/types";

export const STATUSES: readonly Status[] = ["selected", "hypothetical", "implied", "reachable", "maybe", "near", "out"];
export const ROUTE_STATUSES: readonly Tri[] = ["yes", "maybe", "no"];

const STATUS_CLASSES = STATUSES.map(statusClass).join(" ");
const ROUTE_CLASSES = ROUTE_STATUSES.map(routeClass).join(" ");

export function statusClass(status: Status): string {
  return `status-${status}`;
}

export function routeClass(status: Tri): string {
  return `route-${status}`;
}

/**
 * Restyle nodes and edges for a new explore result without touching positions (ADR 0016: status changes never
 * re-run the layout). Edges into or out of a route that works are marked "live".
 */
export function applyStatuses(cy: Core, explore: ExploreResponse | null): void {
  cy.batch(() => {
    cy.elements().removeClass(`${STATUS_CLASSES} ${ROUTE_CLASSES} live`);
    if (!explore) return;
    cy.nodes().forEach((node) => {
      const id = node.id();
      if (node.hasClass("route")) {
        const status = explore.route_status[id];
        if (status) node.addClass(routeClass(status));
        if (status === "yes") node.connectedEdges().addClass("live");
      } else {
        const status = explore.status[id];
        if (status) node.addClass(statusClass(status));
      }
    });
  });
}
