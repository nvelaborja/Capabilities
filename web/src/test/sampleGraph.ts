import type { GraphResponse } from "../api/types";

/**
 * flint → (knap) → knife → is_a blade → (chop) → cut wood
 * wood + knife + cut wood → (make spear) → spear
 */
export const sampleGraph: GraphResponse = {
  nodes: [
    { id: "flint", label: "Flint", kind: "material", origin: "natural", availability: "regional", selectable: true, level: 0 },
    { id: "wood", label: "Wood", kind: "material", origin: "natural", availability: "ubiquitous", selectable: true, level: 0 },
    { id: "knife", label: "Knife", kind: "artifact", selectable: true, level: 1 },
    { id: "blade", label: "Blade", kind: "category", selectable: false, level: 1 },
    { id: "cut:wood", label: "Cut wood", kind: "action", verb: "cut", target: "wood", selectable: true, level: 2 },
    { id: "spear", label: "A very long label for a spear that has to wrap onto more lines", kind: "artifact", selectable: true, level: 3 },
    { id: "laser", label: "Laser", kind: "artifact", era: "modern", selectable: true, level: null },
    { id: "knap", label: "Knapping", kind: "route", achieves: { kind: "thing", id: "knife" } },
    { id: "chop", label: "Chopping", kind: "route", achieves: { kind: "verb", id: "cut" } },
    { id: "make-spear", label: "Make a spear", kind: "route", achieves: { kind: "thing", id: "spear" } },
  ],
  edges: [
    { id: "knap/requires/0", source: "flint", target: "knap", kind: "requires", role: "consumed" },
    { id: "knap/produces/knife", source: "knap", target: "knife", kind: "produces", byproduct: false },
    { id: "knife/is_a/blade", source: "knife", target: "blade", kind: "is_a" },
    { id: "chop/requires/0", source: "blade", target: "chop", kind: "requires", role: "tool" },
    { id: "chop/performs/cut:wood", source: "chop", target: "cut:wood", kind: "performs" },
    { id: "make-spear/requires/0", source: "wood", target: "make-spear", kind: "requires", role: "consumed" },
    { id: "make-spear/requires/1", source: "knife", target: "make-spear", kind: "requires", role: "tool" },
    { id: "make-spear/requires/2", source: "cut:wood", target: "make-spear", kind: "requires", role: "action" },
    { id: "make-spear/produces/spear", source: "make-spear", target: "spear", kind: "produces", byproduct: false },
  ],
  verbs: [{ id: "cut", label: "Cut" }],
  techniques: [],
  actions: [
    { id: "cut:flint", label: "Cut flint" },
    { id: "cut:wood", label: "Cut wood" },
  ],
};
