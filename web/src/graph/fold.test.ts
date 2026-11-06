import cytoscape from "cytoscape";
import { describe, expect, it } from "vitest";

import { sampleGraph } from "../test/sampleGraph";
import { toElements } from "./elements";
import { applyFolding, extraLines, type HubEdge, type HubNode, unfoldAll } from "./fold";
import { FOLDED, isolate } from "./focus";

const node = (id: string, kind: string, level: number | null, prerequisites = 0): HubNode => ({ id, label: id, kind, level, prerequisites });

/** A hub (heat) that helps make `count` things at rising levels. */
function hub(count: number) {
  const products = Array.from({ length: count }, (_, index) => node(`p${index}`, "material", index));
  const nodes = [node("heat", "effect", 2), ...products];
  const edges: HubEdge[] = products.map((p) => ({ id: `heat->${p.id}`, source: "heat", target: p.id }));
  return { nodes, edges };
}

describe("extraLines", () => {
  it("hides nothing when a neighbourhood fits", () => {
    const { nodes, edges } = hub(4);
    expect(extraLines(nodes, edges, 4).size).toBe(0);
  });

  it("keeps lines to the most advanced neighbours and hides the rest", () => {
    // given: heat helps make six things at levels 0–5, with a limit of three
    const { nodes, edges } = hub(6);
    // then: lines to p5, p4 and p3 stay
    expect([...extraLines(nodes, edges, 3)].sort()).toEqual(["heat->p0", "heat->p1", "heat->p2"]);
  });

  it("bounds what a node needs separately from what it helps make", () => {
    // given: steel needs three things and helps make one
    const nodes = [node("steel", "material", 8), node("a", "material", 1), node("b", "material", 2), node("c", "material", 3), node("spear", "artifact", 9)];
    const edges = ["a", "b", "c"].map((id) => ({ id: `${id}->steel`, source: id, target: "steel" }));
    edges.push({ id: "steel->spear", source: "steel", target: "spear" });
    // then: only the inputs are over a limit of two
    expect([...extraLines(nodes, edges, 2)]).toEqual(["a->steel"]);
  });

  it("breaks level ties by certain prerequisites, then name, and puts unknown levels last", () => {
    const nodes = [node("hub", "effect", 0), node("zeta", "material", 3, 9), node("alpha", "material", 3, 1), node("beta", "material", 3, 1), node("laser", "material", null)];
    const edges = nodes.slice(1).map((n) => ({ id: `hub->${n.id}`, source: "hub", target: n.id }));
    expect([...extraLines(nodes, edges, 1)].sort()).toEqual(["hub->alpha", "hub->beta", "hub->laser"]);
  });
});

const headless = () => cytoscape({ headless: true, styleEnabled: false, elements: toElements(sampleGraph) });

describe("folding on the graph", () => {
  it("hides extra lines but never a node, and Expand all shows them again", () => {
    // given: the knife helps make the spear (level 2) and is a blade; with a limit of one, the line to the blade hides
    const cy = headless();
    applyFolding(cy, 1);
    expect(cy.$id("knife/is_a/blade").hasClass(FOLDED)).toBe(true);
    expect(cy.edges(`.${FOLDED}`).length).toBeLessThan(cy.edges().length);
    expect(cy.nodes(`.${FOLDED}`)).toHaveLength(0);
    unfoldAll(cy);
    expect(cy.$(`.${FOLDED}`)).toHaveLength(0);
  });

  it("re-applying with room for everything unfolds what was hidden", () => {
    const cy = headless();
    applyFolding(cy, 1);
    applyFolding(cy);
    expect(cy.$(`.${FOLDED}`)).toHaveLength(0);
  });

  it("counts only what focus mode shows", () => {
    // given: focus on the spear, which needs the knife, cut wood and wood
    const cy = headless();
    isolate(cy, "spear", ["knife", "cut:wood"]);
    applyFolding(cy, 1);
    // then: wood is hidden by focus, so the spear's two showing inputs fold one line, not two
    expect(cy.edges(`.${FOLDED}`).filter((edge) => edge.target().id() === "spear")).toHaveLength(1);
  });
});
