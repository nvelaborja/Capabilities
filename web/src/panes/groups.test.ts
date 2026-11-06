import { describe, expect, it } from "vitest";

import { createCatalog } from "../catalog";
import { exploreWith } from "../test/sampleExplore";
import { sampleGraph } from "../test/sampleGraph";
import { byKind, countChips, groupByVerb, selectedChips, withinReach } from "./groups";

const catalog = createCatalog(sampleGraph);

describe("selectedChips", () => {
  it("holds only what was chosen, sorted by type, then name, and removable", () => {
    // given: a knife and cutting wood chosen, flint implied, and a what-if spear
    const explore = exploreWith({
      selected: ["cut:wood", "knife"],
      hypothetical: ["spear"],
      implied: { things: ["flint"], categories: [], actions: [], techniques: [], effects: {} },
    });
    // then: the spear (labelled "A very long label…") sorts before the knife; flint isn't here
    expect(selectedChips(explore, catalog).map((c) => [c.id, c.status, c.removable])).toEqual([
      ["spear", "hypothetical", true],
      ["knife", "selected", true],
      ["cut:wood", "selected", true],
    ]);
  });
});

describe("withinReach", () => {
  const explore = exploreWith({
    selected: ["knife", "cut:wood"],
    implied: { things: ["flint", "knife"], categories: ["blade"], actions: [], techniques: [], effects: {} },
    implied_by: { flint: ["knife"], blade: ["cut:wood"] },
    implied_effects: [{ id: "heat", label: "Heat", conditions: ["Temperature ≥ 1085 °C"] }],
    reachable: ["spear", "flint"],
    maybe: ["laser"],
    actions: { cut: { wood: "yes", flint: "maybe" } },
    near: [{ id: "wood", label: "Wood", routes: [{ id: "r", label: "R", missing: { id: "flint", label: "Flint", kind: "material" } }] }],
  });
  const sections = withinReach(explore, catalog);
  const section = (key: string) => sections.find((s) => s.key === key);

  it("lists implied items first, then what could be made, what could be done, and what is one step away", () => {
    expect(sections.map((s) => s.title)).toEqual(["Implied", "Could make", "Could do", "One step away"]);
  });

  it("puts implied items here, not with the selection, and never repeats a chosen or implied item", () => {
    expect(section("implied")?.chips.map((c) => c.id)).toEqual(["flint", "blade", "heat"]);
    expect(section("implied")?.chips[0]).toMatchObject({ status: "implied", removable: false, title: "Needed by knife" });
    expect(section("reachable")?.chips.map((c) => c.id)).toEqual(["spear", "laser"]);
  });

  it("marks maybes, leaves out actions already chosen, and says what a near miss needs", () => {
    expect(section("reachable")?.chips[1]).toMatchObject({ id: "laser", status: "maybe", note: "maybe" });
    expect(section("actions")?.chips.map((c) => [c.label, c.status])).toEqual([["Cut flint", "maybe"]]);
    expect(section("actions")?.groups).toEqual([]);
    expect(section("near")?.chips[0]).toMatchObject({ status: "near", note: "add flint" });
    expect(countChips(sections)).toBe(7);
  });

  it("shows the level an implied effect reaches", () => {
    expect(section("implied")?.chips.at(-1)).toMatchObject({ label: "Heat", note: "Temperature ≥ 1085 °C" });
  });
});

describe("groupByVerb", () => {
  const action = (id: string, status: "reachable" | "maybe" = "reachable") => ({ id, label: catalog.get(id).label, kind: "action" as const, status, removable: false });

  it("folds a verb's targets into one chip that counts them, and leaves a verb with one target alone", () => {
    // given: cut has two targets (one a maybe), move has one
    const { groups, single } = groupByVerb([action("cut:wood"), action("cut:flint", "maybe"), action("move:(any)")], catalog);
    // then: cut becomes "Cut · 2 materials (1 maybe)"; move stays a plain chip
    expect(groups).toMatchObject([{ key: "cut", label: "Cut", status: "reachable", note: "2 materials (1 maybe)" }]);
    expect(groups[0]?.chips.map((c) => c.id)).toEqual(["cut:flint", "cut:wood"]);
    expect(single.map((c) => c.id)).toEqual(["move:(any)"]);
  });

  it("marks a group maybe only when every target is a maybe", () => {
    const { groups } = groupByVerb([action("cut:wood", "maybe"), action("cut:flint", "maybe")], catalog);
    expect(groups[0]).toMatchObject({ status: "maybe", note: "2 materials" });
  });

  it("counts folded chips with the rest", () => {
    const { groups } = groupByVerb([action("cut:wood"), action("cut:flint")], catalog);
    expect(countChips([{ key: "a", title: "A", groups, chips: [action("move:(any)")] }])).toBe(3);
  });
});

describe("byKind", () => {
  it("splits sorted chips into runs of one type", () => {
    const chip = (id: string, kind: "material" | "artifact") => ({ id, label: id, kind, status: "reachable" as const, removable: false });
    expect(byKind([chip("a", "material"), chip("b", "material"), chip("c", "artifact")]).map((run) => run.map((c) => c.id))).toEqual([
      ["a", "b"],
      ["c"],
    ]);
  });
});
