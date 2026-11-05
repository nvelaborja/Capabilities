import { describe, expect, it } from "vitest";

import { createCatalog } from "../catalog";
import { exploreWith } from "../test/sampleExplore";
import { sampleGraph } from "../test/sampleGraph";
import { countRows, reachableGroups, selectedGroups } from "./groups";

const catalog = createCatalog(sampleGraph);

describe("selectedGroups", () => {
  const explore = exploreWith({
    selected: ["knife", "cut:wood"],
    implied: { things: ["flint", "knife"], categories: ["blade"], actions: [], techniques: [], effects: {} },
    implied_by: { flint: ["knife"], blade: ["cut:wood"] },
    implied_effects: [{ id: "heat", label: "Heat", conditions: ["Temperature ≥ 1085 °C"] }],
  });

  it("groups by type in a fixed order, explicit and implied together", () => {
    const groups = selectedGroups(explore, catalog);
    expect(groups.map((g) => g.title)).toEqual(["Materials", "Tools and products", "Actions", "Any of a kind", "Conditions reached"]);
  });

  it("marks implied items, says what needs them, and lets only explicit ones be removed", () => {
    const rows = selectedGroups(explore, catalog).flatMap((g) => g.rows);
    expect(rows.find((r) => r.id === "flint")).toMatchObject({ badge: "implied", removable: false, note: "Needed by knife" });
    expect(rows.find((r) => r.id === "knife")).toMatchObject({ removable: true });
    expect(rows.filter((r) => r.id === "knife")).toHaveLength(1); // explicit wins over implied
  });

  it("shows implied effect levels readably", () => {
    const rows = selectedGroups(explore, catalog).flatMap((g) => g.rows);
    expect(rows.find((r) => r.id === "heat")?.label).toBe("Heat (temperature ≥ 1085 °c)");
  });
});

describe("reachableGroups", () => {
  it("lists reachable and maybe things, then actions by verb, leaving out what is already selected", () => {
    const explore = exploreWith({
      selected: ["cut:wood"],
      reachable: ["spear"],
      maybe: ["laser"],
      actions: { cut: { wood: "yes", flint: "maybe" } },
    });
    const groups = reachableGroups(explore, catalog);
    expect(groups.map((g) => g.title)).toEqual(["Tools and products", "Cut"]);
    expect(groups[1]?.rows).toEqual([{ id: "cut:flint", label: "Cut flint", removable: false, badge: "maybe" }]);
    expect(countRows(groups)).toBe(3);
  });

  it("sorts by label, not by id", () => {
    // given: the spear's label starts with "A very long label", so it sorts before "Knife" despite its id
    const explore = exploreWith({ reachable: ["knife", "spear"] });
    expect(reachableGroups(explore, catalog)[0]?.rows.map((r) => r.id)).toEqual(["spear", "knife"]);
  });
});
