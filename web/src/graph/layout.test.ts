import cytoscape from "cytoscape";
import { describe, expect, it } from "vitest";

import { sampleGraph } from "../test/sampleGraph";
import { toElements } from "./elements";
import { COLUMN_GAP, READABLE_ZOOM, resolveRanks, runLayout, showInitialView, sortColumn, stackColumn } from "./layout";

const headless = () => cytoscape({ headless: true, styleEnabled: false, elements: toElements(sampleGraph) });

describe("resolveRanks", () => {
  it("uses tech levels", () => {
    expect(resolveRanks(headless()).get("knife")).toBe(1);
  });

  it("places things without a level next to what they connect to, or in the first column", () => {
    // given: a modern saw with no level that cuts granite (level 5), and an unconnected laser
    const cy = cytoscape({
      headless: true,
      styleEnabled: false,
      elements: [
        { data: { id: "saw", rank: null } },
        { data: { id: "cut-granite", rank: 5 } },
        { data: { id: "laser", rank: null } },
        { data: { id: "saw->cut-granite", source: "saw", target: "cut-granite" } },
      ],
    });
    const ranks = resolveRanks(cy);
    expect(ranks.get("saw")).toBe(4);
    expect(ranks.get("laser")).toBe(0);
  });
});

const item = (id: string, kind: string, label = id, height = 30) => ({ id, kind, label, height });

describe("sortColumn", () => {
  it("sorts by type, then alphabetically ignoring case", () => {
    const sorted = sortColumn([
      item("heat", "effect", "Heat"),
      item("saw", "artifact", "saw"),
      item("axe", "artifact", "Axe"),
      item("cut", "action", "Cut wood"),
      item("wood", "material", "Wood"),
    ]);
    expect(sorted.map((i) => i.id)).toEqual(["wood", "axe", "saw", "cut", "heat"]);
  });
});

describe("stackColumn", () => {
  it("stacks in order, centred on zero, with extra space where the type changes", () => {
    const placed = stackColumn([item("a", "material"), item("b", "material"), item("c", "artifact")]);
    const at = (id: string) => placed.get(id) ?? Number.NaN;
    const [a, b, c] = [at("a"), at("b"), at("c")];
    expect(b - a).toBe(30 + 14);
    expect(c - b).toBe(30 + 14 + 18);
    // centred: the top of a and the bottom of c are equally far from zero
    expect((a - 15 + (c + 15)) / 2).toBeCloseTo(0);
  });
});

describe("runLayout", () => {
  it("orders each column by type, then name", () => {
    // given: level 0 holds two materials (flint, wood); level 1 holds a knife (tool) and a blade (category)
    const cy = headless();
    runLayout(cy);
    expect(cy.$id("flint").position("y")).toBeLessThan(cy.$id("wood").position("y"));
    expect(cy.$id("knife").position("y")).toBeLessThan(cy.$id("blade").position("y"));
  });

  it("puts each node in its tech-level column, primitives on the left", () => {
    const cy = headless();
    runLayout(cy);
    expect(cy.$id("flint").position("x")).toBe(0);
    expect(cy.$id("knife").position("x")).toBe(COLUMN_GAP);
    expect(cy.$id("spear").position("x")).toBe(3 * COLUMN_GAP);
  });

  it("labels each level's column", () => {
    const cy = headless();
    runLayout(cy);
    expect(cy.$(".level-label").map((n) => n.data("label") as string)).toEqual(["Level 0", "Level 1", "Level 2", "Level 3"]);
  });

  it("doesn't stack labels when run twice", () => {
    const cy = headless();
    runLayout(cy);
    runLayout(cy);
    expect(cy.$(".level-label")).toHaveLength(4);
  });
});

describe("showInitialView", () => {
  it("zooms to a readable size when fitting everything would make labels too small", () => {
    const cy = headless();
    cy.nodes().forEach((node, index) => {
      node.position({ x: index * 2000, y: 0 });
    });
    showInitialView(cy);
    expect(cy.zoom()).toBeGreaterThanOrEqual(READABLE_ZOOM);
  });
});
