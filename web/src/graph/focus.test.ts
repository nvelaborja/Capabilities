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
  it("includes what a thing needs, what it helps make, and the categories it belongs to", () => {
    // given: a knife is knapped from flint, is a blade, and helps make a spear
    const cy = headlessGraph();
    // then: cut wood (which only the blade category leads to) is two steps away and left out
    expect(ids(neighbourhood(cy.$id("knife")))).toEqual(["blade", "flint", "knife", "spear"]);
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
    expect(cy.$(".faded, .focused, .highlighted")).toHaveLength(0);
  });

  it("brings the neighbourhood's edges forward and fades the rest", () => {
    const cy = headlessGraph();
    focusOn(cy.$id("knife"));
    expect(cy.$id("knife->spear").hasClass("highlighted")).toBe(true);
    expect(cy.$id("blade->cut:wood").hasClass("highlighted")).toBe(false);
    expect(cy.$id("blade->cut:wood").hasClass("faded")).toBe(true);
  });
});
