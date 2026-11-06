import cytoscape from "cytoscape";
import { describe, expect, it } from "vitest";

import { sampleGraph } from "../test/sampleGraph";
import { toElements } from "./elements";
import { applySummaries, expandSummary } from "./fold";
import { FOLDED, isolate } from "./focus";

const headless = () => cytoscape({ headless: true, styleEnabled: false, elements: toElements(sampleGraph) });

describe("summary nodes on the graph", () => {
  it("folds a hub's extra edges into a summary node linked to the hub, and never removes a real node", () => {
    // given: the knife helps make the spear and is a blade; with a limit of one, one of those folds away
    const cy = headless();
    const before = cy.nodes().length;
    const summaries = applySummaries(cy, new Set(), 1);
    const knife = summaries.find((s) => s.hub === "knife" && s.direction === "out");
    // then: the spear (higher level) stays linked; the blade's edge folds into "1 other kind of thing"
    expect(knife?.label).toBe("1 other kind of thing");
    expect(cy.$id("knife/is_a/blade").hasClass(FOLDED)).toBe(true);
    expect(knife?.edges).toEqual(["knife/is_a/blade"]);
    expect(cy.$id(`${knife?.id}/edge`).source().id()).toBe("knife");
    expect(cy.nodes().not(".summary")).toHaveLength(before);
  });

  it("expands one summary in place and leaves the others", () => {
    const cy = headless();
    const expanded = new Set<string>();
    const summaries = applySummaries(cy, expanded, 1);
    const knife = summaries.find((s) => s.hub === "knife" && s.direction === "out");
    if (!knife) throw new Error("expected a knife summary");
    expandSummary(cy, summaries, expanded, knife.id);
    expect(cy.$id(knife.id).empty()).toBe(true);
    expect(cy.$id("knife/is_a/blade").hasClass(FOLDED)).toBe(false);
    expect(cy.$(".summary").length).toBe(summaries.length - 1);
  });

  it("draws nothing extra when every neighbourhood fits, and re-applying replaces the old summaries", () => {
    const cy = headless();
    applySummaries(cy, new Set(), 1);
    expect(applySummaries(cy, new Set())).toEqual([]);
    expect(cy.$(".summary, .folded")).toHaveLength(0);
  });

  it("summarises only what focus mode shows", () => {
    // given: focus on cut wood hides wood and its edge to the spear
    const cy = headless();
    isolate(cy, "cut:wood");
    const hubs = applySummaries(cy, new Set(), 1).map((s) => s.hub);
    // then: the spear's inputs are only knife and cut wood (wood is hidden), so with a limit of one, it folds one
    expect(hubs).not.toContain("wood");
    expect(cy.$(".summary").every((node) => node.data("members").every((id: string) => id !== "wood"))).toBe(true);
  });
});
