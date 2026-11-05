import { describe, expect, it } from "vitest";

import { sampleGraph } from "../test/sampleGraph";
import { edgeClasses, layoutRank, nodeClasses, nodeSize, toElements } from "./elements";

const node = (id: string) => {
  const found = sampleGraph.nodes.find((n) => n.id === id);
  if (!found) throw new Error(`no node ${id}`);
  return found;
};

describe("nodeSize", () => {
  it("draws routes as small dots", () => {
    expect(nodeSize(node("knap"))).toEqual({ width: 10, height: 10 });
  });

  it("caps the width of long labels and adds lines instead", () => {
    // given: a label far wider than one line
    const size = nodeSize(node("spear"));
    // then: the width stops at the maximum and the node grows taller
    expect(size.width).toBe(168);
    expect(size.height).toBeGreaterThan(nodeSize(node("knife")).height);
  });

  it("draws ubiquitous materials smaller than other materials", () => {
    expect(nodeSize(node("wood")).height).toBeLessThan(nodeSize(node("flint")).height);
  });
});

describe("classes", () => {
  it.each([
    ["wood", ["material", "ubiquitous", "selectable"]],
    ["flint", ["material", "selectable"]],
    ["blade", ["category"]],
    ["laser", ["artifact", "modern", "selectable"]],
  ])("gives %s the classes %j", (id, classes) => {
    expect(nodeClasses(node(id))).toEqual(classes);
  });

  it("marks edges with their kind and requirement role", () => {
    const tool = sampleGraph.edges.find((e) => e.id === "make-spear/requires/1");
    expect(tool && edgeClasses(tool)).toEqual(["requires", "role-tool"]);
  });
});

describe("toElements", () => {
  it("keeps every node and edge with its endpoints", () => {
    const elements = toElements(sampleGraph);
    expect(elements).toHaveLength(sampleGraph.nodes.length + sampleGraph.edges.length);
    const edge = elements.find((e) => e.data.id === "knap/produces/knife");
    expect(edge?.data).toMatchObject({ source: "knap", target: "knife" });
  });
});

describe("layoutRank", () => {
  it("puts things at twice their level and routes one column right of their requirements", () => {
    expect(layoutRank(node("knife"))).toBe(2);
    expect(layoutRank({ ...node("knap"), level: 0 })).toBe(1);
  });

  it("leaves nodes without a level unranked", () => {
    expect(layoutRank(node("laser"))).toBeNull();
    expect(layoutRank(node("chop"))).toBeNull();
  });
});
