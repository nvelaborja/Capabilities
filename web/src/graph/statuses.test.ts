import cytoscape from "cytoscape";
import { describe, expect, it } from "vitest";

import type { ExploreResponse } from "../api/types";
import { exploreWith as sampleExplore } from "../test/sampleExplore";
import { sampleGraph } from "../test/sampleGraph";
import { toElements } from "./elements";
import { applyStatuses } from "./statuses";

function headlessGraph() {
  return cytoscape({ headless: true, styleEnabled: false, elements: toElements(sampleGraph) });
}

function exploreWith(status: ExploreResponse["status"], routeStatus: ExploreResponse["route_status"] = {}): ExploreResponse {
  return sampleExplore({ status, route_status: routeStatus });
}

describe("applyStatuses", () => {
  it("adds one status class per node", () => {
    const cy = headlessGraph();
    applyStatuses(cy, exploreWith({ knife: "selected", flint: "implied", spear: "near" }));
    expect(cy.$id("knife").hasClass("status-selected")).toBe(true);
    expect(cy.$id("flint").hasClass("status-implied")).toBe(true);
    expect(cy.$id("spear").hasClass("status-near")).toBe(true);
  });

  it("replaces the previous statuses rather than adding to them", () => {
    const cy = headlessGraph();
    applyStatuses(cy, exploreWith({ knife: "selected" }));
    applyStatuses(cy, exploreWith({ knife: "reachable" }));
    expect(cy.$id("knife").classes()).not.toContain("status-selected");
    expect(cy.$id("knife").hasClass("status-reachable")).toBe(true);
  });

  it("marks the edges of working routes as live", () => {
    // given: knapping works, making a spear doesn't
    const cy = headlessGraph();
    applyStatuses(cy, exploreWith({}, { knap: "yes", "make-spear": "no" }));
    // then: knapping's edges are live and the spear route's are not
    expect(cy.$id("knap/requires/0").hasClass("live")).toBe(true);
    expect(cy.$id("knap/produces/knife").hasClass("live")).toBe(true);
    expect(cy.$id("make-spear/produces/spear").hasClass("live")).toBe(false);
    expect(cy.$id("make-spear").hasClass("route-no")).toBe(true);
  });

  it("clears everything when there is no result", () => {
    const cy = headlessGraph();
    applyStatuses(cy, exploreWith({ knife: "selected" }, { knap: "yes" }));
    applyStatuses(cy, null);
    expect(cy.$(".status-selected, .route-yes, .live")).toHaveLength(0);
  });
});
