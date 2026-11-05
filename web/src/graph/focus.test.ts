import cytoscape, { type Collection } from "cytoscape";
import { describe, expect, it } from "vitest";

import { sampleGraph } from "../test/sampleGraph";
import { toElements } from "./elements";
import { clearFocus, focusOn, neighbourhood } from "./focus";

function headlessGraph() {
  return cytoscape({ headless: true, styleEnabled: false, elements: toElements(sampleGraph) });
}

const ids = (collection: Collection) => collection.nodes().map((n) => n.id()).sort();

describe("neighbourhood", () => {
  it("reaches one route out in each direction, plus the categories a thing belongs to", () => {
    // given: knife is made by knapping flint, is a blade, and is used to make a spear
    const cy = headlessGraph();
    // then: flint and the spear are included, but not what the blade category feeds (chopping, cut wood)
    expect(ids(neighbourhood(cy.$id("knife")))).toEqual(["blade", "flint", "knap", "knife", "make-spear", "spear"]);
  });

  it("shows a category's members", () => {
    const cy = headlessGraph();
    expect(ids(neighbourhood(cy.$id("blade")))).toContain("knife");
  });
});

describe("focus", () => {
  it("fades everything outside the neighbourhood, and clearing restores it", () => {
    const cy = headlessGraph();
    focusOn(cy.$id("knife"));
    expect(cy.$id("cut:wood").hasClass("faded")).toBe(true);
    expect(cy.$id("spear").hasClass("faded")).toBe(false);
    expect(cy.$id("knife").hasClass("focused")).toBe(true);
    clearFocus(cy);
    expect(cy.$(".faded, .focused")).toHaveLength(0);
  });
});
