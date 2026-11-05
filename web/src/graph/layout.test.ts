import cytoscape from "cytoscape";
import { describe, expect, it } from "vitest";

import { sampleGraph } from "../test/sampleGraph";
import { toElements } from "./elements";
import {
  COLUMN_GAP,
  minimumLength,
  orderByBarycentre,
  READABLE_ZOOM,
  resolveRanks,
  runLayout,
  showInitialView,
  stackColumn,
} from "./layout";

const headless = () => cytoscape({ headless: true, styleEnabled: false, elements: toElements(sampleGraph) });

describe("minimumLength", () => {
  it("asks for the gap between the two columns", () => {
    expect(minimumLength(0, 3)).toBe(3);
  });

  it.each([
    [5, 2],
    [null, 4],
    [4, null],
  ])("falls back to one column for backward or unranked edges (%s → %s)", (source, target) => {
    expect(minimumLength(source, target)).toBe(1);
  });
});

describe("resolveRanks", () => {
  it("uses tech levels and places unranked routes right of what feeds them", () => {
    // given: knife is level 1 (rank 2); the chopping route has no level and is fed by the blade category (rank 2)
    const ranks = resolveRanks(headless());
    expect(ranks.get("knife")).toBe(2);
    expect(ranks.get("chop")).toBe(3);
  });

  it("places unranked things left of what they feed, or in the first column", () => {
    const ranks = resolveRanks(headless());
    expect(ranks.get("laser")).toBe(0); // feeds nothing and is fed by nothing
  });
});

describe("stackColumn", () => {
  it("stacks nodes in order, a gap apart, centred on zero", () => {
    const placed = stackColumn(
      [
        { id: "a", height: 30 },
        { id: "b", height: 50 },
      ],
      10,
    );
    // total height 90: a spans -45..-15, b spans -5..45
    expect(placed.get("a")).toBe(-30);
    expect(placed.get("b")).toBe(20);
  });
});

describe("orderByBarycentre", () => {
  it("lines nodes up with their neighbours to reduce crossings", () => {
    // given: column 0 has top, bottom; column 1 has x (fed by bottom) above y (fed by top), so the links cross
    const columns = new Map([
      [0, ["top", "bottom"]],
      [1, ["x", "y"]],
    ]);
    const ranks = new Map([["top", 0], ["bottom", 0], ["x", 1], ["y", 1]]);
    const links: [string, string][] = [
      ["bottom", "x"],
      ["top", "y"],
    ];
    // when: reordering
    const ordered = orderByBarycentre(columns, ranks, links);
    // then: the crossing is gone
    const column0 = ordered.get(0) ?? [];
    const column1 = ordered.get(1) ?? [];
    expect(column0.indexOf("top") < column0.indexOf("bottom")).toBe(column1.indexOf("y") < column1.indexOf("x"));
  });
});

describe("runLayout", () => {
  it("puts each node in its tech-level column, primitives on the left", () => {
    const cy = headless();
    runLayout(cy);
    expect(cy.$id("flint").position("x")).toBe(0);
    expect(cy.$id("knife").position("x")).toBe(2 * COLUMN_GAP);
    expect(cy.$id("spear").position("x")).toBe(6 * COLUMN_GAP);
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
