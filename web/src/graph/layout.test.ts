import cytoscape from "cytoscape";
import { describe, expect, it } from "vitest";

import { sampleGraph } from "../test/sampleGraph";
import { toElements } from "./elements";
import { minimumLength, READABLE_ZOOM, showInitialView } from "./layout";

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

describe("showInitialView", () => {
  it("zooms to a readable size when fitting everything would make labels too small", () => {
    // given: nodes spread far apart in a small viewport
    const cy = cytoscape({ headless: true, styleEnabled: false, elements: toElements(sampleGraph) });
    cy.nodes().forEach((node, index) => {
      node.position({ x: index * 2000, y: 0 });
    });
    // when: showing the first view
    showInitialView(cy);
    // then: it does not zoom out past the readable level
    expect(cy.zoom()).toBeGreaterThanOrEqual(READABLE_ZOOM);
  });
});
