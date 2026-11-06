import { describe, expect, it } from "vitest";

import { sampleGraph } from "../test/sampleGraph";
import { drawnEdges, edgeClasses, layoutRank, nodeClasses, nodeSize, STRIP_WIDTH, toElements } from "./elements";

const node = (id: string) => {
  const found = sampleGraph.nodes.find((n) => n.id === id);
  if (!found) throw new Error(`no node ${id}`);
  return found;
};

describe("nodeSize", () => {
  it("caps the width of long labels and adds lines instead", () => {
    // given: a label far wider than one line
    const size = nodeSize(node("spear"));
    // then: the width stops at the maximum (plus the type strip) and the node grows taller
    expect(size.width).toBe(168 + STRIP_WIDTH);
    expect(size.height).toBeGreaterThan(nodeSize(node("knife")).height);
  });

  it("draws ubiquitous materials smaller than other materials", () => {
    expect(nodeSize(node("wood")).height).toBeLessThan(nodeSize(node("flint")).height);
  });
});

describe("nodeClasses", () => {
  it.each([
    ["wood", ["material", "ubiquitous", "selectable"]],
    ["flint", ["material", "selectable"]],
    ["blade", ["category"]],
    ["laser", ["artifact", "modern", "selectable"]],
  ])("gives %s the classes %j", (id, classes) => {
    expect(nodeClasses(node(id))).toEqual(classes);
  });
});

describe("drawnEdges", () => {
  const edges = drawnEdges(sampleGraph);
  const pairs = edges.map((e) => `${e.source}->${e.target}`).sort();

  it("draws each requirement straight to what its route makes, with no route junctions", () => {
    expect(pairs).toEqual([
      "blade->cut:wood", "cut:wood->spear", "flint->knife", "knife->blade", "knife->spear", "wood->spear",
    ]);
  });

  it("keeps the role and the route behind each edge", () => {
    const tool = edges.find((e) => e.id === "knife->spear");
    expect(tool).toMatchObject({ roles: ["tool"], routes: ["make-spear"], byproduct: false });
    expect(tool && edgeClasses(tool)).toEqual(["requires", "role-tool"]);
  });

  it("merges routes that link the same pair, keeping every route, role and label", () => {
    // given: two routes that both turn flint into a knife, one needing heat
    const graph = {
      ...sampleGraph,
      nodes: [...sampleGraph.nodes, { id: "grind", label: "Grinding", kind: "route" as const }],
      edges: [
        ...sampleGraph.edges,
        { id: "grind/requires/0", source: "flint", target: "grind", kind: "requires" as const, role: "tool" as const, label: "Hardness ≥ 7" },
        { id: "grind/produces/knife", source: "grind", target: "knife", kind: "produces" as const },
      ],
    };
    const merged = drawnEdges(graph).filter((e) => e.id === "flint->knife");
    expect(merged).toHaveLength(1);
    expect(merged[0]).toMatchObject({ routes: ["knap", "grind"], roles: ["consumed", "tool"], labels: ["Hardness ≥ 7"] });
    // mixed roles get no dash style
    expect(merged[0] && edgeClasses(merged[0])).toEqual(["requires"]);
  });

  it("marks lines that only lead to byproducts", () => {
    const graph = {
      ...sampleGraph,
      nodes: [...sampleGraph.nodes, { id: "chips", label: "Chips", kind: "material" as const }],
      edges: [...sampleGraph.edges, { id: "knap/produces/chips", source: "knap", target: "chips", kind: "produces" as const, byproduct: true }],
    };
    const chips = drawnEdges(graph).find((e) => e.id === "flint->chips");
    expect(chips?.byproduct).toBe(true);
    expect(drawnEdges(graph).find((e) => e.id === "flint->knife")?.byproduct).toBe(false);
  });
});

describe("toElements", () => {
  it("leaves out route junctions and keeps every other node", () => {
    const elements = toElements(sampleGraph);
    const nodeIds = elements.filter((e) => e.group === "nodes").map((e) => e.data.id);
    expect(nodeIds).not.toContain("knap");
    expect(nodeIds).toHaveLength(sampleGraph.nodes.filter((n) => n.kind !== "route").length);
    expect(elements.find((e) => e.data.id === "knife->spear")?.data).toMatchObject({ routes: ["make-spear"] });
  });
});

describe("layoutRank", () => {
  it("is the tech level, or null when unknown", () => {
    expect(layoutRank(node("knife"))).toBe(1);
    expect(layoutRank(node("laser"))).toBeNull();
  });
});
