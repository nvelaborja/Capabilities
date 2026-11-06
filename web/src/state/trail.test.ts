import { describe, expect, it } from "vitest";

import { current, type Trail, trailReducer } from "./trail";

const run = (...actions: Parameters<typeof trailReducer>[1][]): Trail => actions.reduce(trailReducer, [] as Trail);

describe("detail trail", () => {
  it("drills down from an opened node and goes back along the breadcrumb", () => {
    // given: steel opened, then bloom iron and iron ore drilled into
    const trail = run({ type: "open", id: "steel" }, { type: "drill", id: "bloom-iron" }, { type: "drill", id: "iron-ore" });
    expect(trail).toEqual(["steel", "bloom-iron", "iron-ore"]);
    expect(current(trail)).toBe("iron-ore");
    // when: going back to the first crumb
    // then: the trail ends at steel
    expect(trailReducer(trail, { type: "back", index: 0 })).toEqual(["steel"]);
  });

  it("starts a new trail when another node is opened from the graph, a list or search", () => {
    const trail = run({ type: "open", id: "steel" }, { type: "drill", id: "bloom-iron" }, { type: "open", id: "copper" });
    expect(trail).toEqual(["copper"]);
  });

  it("returns to a node already on the trail instead of looping", () => {
    const trail = run({ type: "open", id: "charcoal" }, { type: "drill", id: "heat" }, { type: "drill", id: "charcoal" });
    expect(trail).toEqual(["charcoal"]);
  });

  it("keeps the same trail object when nothing changes, so React skips a render", () => {
    const trail = run({ type: "open", id: "steel" });
    expect(trailReducer(trail, { type: "open", id: "steel" })).toBe(trail);
    expect(trailReducer(trail, { type: "back", index: 0 })).toBe(trail);
    expect(trailReducer([], { type: "close" })).toEqual([]);
  });

  it("closes to an empty trail", () => {
    const trail = run({ type: "open", id: "steel" }, { type: "close" });
    expect(current(trail)).toBeNull();
  });
});
