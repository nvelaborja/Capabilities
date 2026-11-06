import { describe, expect, it } from "vitest";

import { foldedEdges, type HubEdge, type HubNode, summarise } from "./summaries";

const node = (id: string, kind: string, level: number | null, prerequisites = 0): HubNode => ({ id, label: id, kind, level, prerequisites });

/** A hub (heat) that helps make `count` things, alternating tools and materials, at rising levels. */
function hub(count: number) {
  const products = Array.from({ length: count }, (_, index) => node(`p${index}`, index % 2 ? "material" : "artifact", index));
  const nodes = [node("heat", "effect", 2), ...products];
  const edges: HubEdge[] = products.map((p) => ({ id: `heat->${p.id}`, source: "heat", target: p.id }));
  return { nodes, edges };
}

describe("summarise", () => {
  it("leaves a neighbourhood that fits alone", () => {
    const { nodes, edges } = hub(4);
    expect(summarise(nodes, edges, 4)).toEqual([]);
  });

  it("keeps the most advanced neighbours and folds the rest into one summary per kind", () => {
    // given: heat helps make six things at levels 0–5, with a limit of three
    const { nodes, edges } = hub(6);
    // when: summarising
    const summaries = summarise(nodes, edges, 3);
    // then: p5, p4, p3 stay; p2 and p0 (tools) and p1 (a material) fold away, by kind
    expect(summaries.map((s) => [s.label, s.members])).toEqual([
      ["2 other tools and products", ["p2", "p0"]],
      ["1 other material", ["p1"]],
    ]);
    expect(summaries[0]).toMatchObject({ hub: "heat", direction: "out", edges: ["heat->p2", "heat->p0"] });
  });

  it("bounds what a node needs separately from what it helps make", () => {
    // given: steel needs three things and helps make one
    const nodes = [node("steel", "material", 8), node("a", "material", 1), node("b", "material", 2), node("c", "material", 3), node("spear", "artifact", 9)];
    const edges = ["a", "b", "c"].map((id) => ({ id: `${id}->steel`, source: id, target: "steel" }));
    edges.push({ id: "steel->spear", source: "steel", target: "spear" });
    // then: only the inputs are over a limit of two
    expect(summarise(nodes, edges, 2).map((s) => [s.id, s.members])).toEqual([["summary:in:steel:material", ["a"]]]);
  });

  it("breaks level ties by certain prerequisites, then name, and puts unknown levels last", () => {
    const nodes = [node("hub", "effect", 0), node("zeta", "material", 3, 9), node("alpha", "material", 3, 1), node("beta", "material", 3, 1), node("laser", "material", null)];
    const edges = nodes.slice(1).map((n) => ({ id: `hub->${n.id}`, source: "hub", target: n.id }));
    expect(summarise(nodes, edges, 1)[0]?.members).toEqual(["alpha", "beta", "laser"]);
  });
});

describe("foldedEdges", () => {
  it("hides an edge until every summary holding it is expanded", () => {
    const summaries = [
      { id: "s1", hub: "a", direction: "out" as const, kind: "material", label: "", members: ["b"], edges: ["a->b", "a->c"] },
      { id: "s2", hub: "b", direction: "in" as const, kind: "material", label: "", members: ["a"], edges: ["a->b"] },
    ];
    expect([...foldedEdges(summaries, new Set())].sort()).toEqual(["a->b", "a->c"]);
    expect([...foldedEdges(summaries, new Set(["s1"]))]).toEqual(["a->b"]);
    expect(foldedEdges(summaries, new Set(["s1", "s2"])).size).toBe(0);
  });
});
