import cytoscape, { type Collection } from "cytoscape";
import { describe, expect, it } from "vitest";

import { sampleGraph } from "../test/sampleGraph";
import { toElements } from "./elements";
import { clearFocus, findEdge, focusOn, focusOnEdge, FOLDED, isolate, lineage, neighbourhood, OUTSIDE, REVEALED } from "./focus";

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

  it("includes neighbours whose line is folded, since clicking the node draws it", () => {
    const cy = headlessGraph();
    cy.$id("knife->spear").addClass(FOLDED);
    expect(ids(neighbourhood(cy.$id("knife")))).toContain("spear");
  });
});

describe("lineage (focus mode)", () => {
  it("holds the node, what it certainly needs, and what it directly helps make", () => {
    // given: cut wood certainly needs a blade (any blade will do) and helps make the spear
    const cy = headlessGraph();
    // then: the knife and flint (one way to have a blade) are left out, and so is wood (only the spear needs it)
    expect(ids(lineage(cy.$id("cut:wood"), ["blade"]))).toEqual(["blade", "cut:wood", "spear"]);
  });

  it("keeps only the lines between what it shows", () => {
    const cy = headlessGraph();
    const lines = lineage(cy.$id("cut:wood"), ["blade"]).edges().map((edge) => edge.id());
    expect(lines).toContain("blade->cut:wood");
    expect(lines).not.toContain("knife/is_a/blade");
  });

  it("hides everything else, and showing the whole graph brings it back", () => {
    const cy = headlessGraph();
    isolate(cy, "cut:wood", ["blade"]);
    expect(cy.$id("knife").hasClass(OUTSIDE)).toBe(true);
    expect(cy.$id("wood").hasClass(OUTSIDE)).toBe(true);
    expect(cy.$id("wood->spear").hasClass(OUTSIDE)).toBe(true);
    expect(cy.$id("blade->cut:wood").hasClass(OUTSIDE)).toBe(false);
    isolate(cy, null);
    expect(cy.$(`.${OUTSIDE}`)).toHaveLength(0);
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

  it("draws a busy node's hidden lines while it is clicked, and hides them again after", () => {
    // given: the knife's line to the spear is folded away
    const cy = headlessGraph();
    cy.$id("knife->spear").addClass(FOLDED);
    // when: the knife is clicked
    focusOn(cy.$id("knife"));
    // then: the line is drawn, and only until the focus clears
    expect(cy.$id("knife->spear").hasClass(REVEALED)).toBe(true);
    clearFocus(cy);
    expect(cy.$id("knife->spear").hasClass(REVEALED)).toBe(false);
  });
});

describe("focus on a line", () => {
  it("brings the line and its two ends forward and fades everything else", () => {
    const cy = headlessGraph();
    const edge = findEdge(cy, "knife", "spear");
    if (!edge) throw new Error("expected a line from knife to spear");
    focusOnEdge(edge);
    expect(edge.hasClass("focused-edge")).toBe(true);
    expect(cy.$id("knife").hasClass("focused") && cy.$id("spear").hasClass("focused")).toBe(true);
    expect(cy.$id("flint").hasClass("faded")).toBe(true);
    clearFocus(cy);
    expect(cy.$(".focused-edge, .faded")).toHaveLength(0);
  });

  it("finds is-a lines too, and nothing where no line is drawn", () => {
    const cy = headlessGraph();
    expect(findEdge(cy, "knife", "blade")?.id()).toBe("knife/is_a/blade");
    expect(findEdge(cy, "flint", "spear")).toBeNull();
  });
});
