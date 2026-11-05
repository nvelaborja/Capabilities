import { describe, expect, it } from "vitest";

import { decodeSelection, encodeSelection } from "./url";

describe("shareable links", () => {
  it("round-trips a preset with additions and removals, readably", () => {
    const selection = { preset: "middle-kingdom-egypt", added: ["cut:wood", "hematite"], removed: ["sledge"] };
    const query = encodeSelection(selection);
    expect(query).toBe("?preset=middle-kingdom-egypt&add=cut:wood,hematite&remove=sledge");
    expect(decodeSelection(query)).toEqual(selection);
  });

  it("is empty for an empty selection", () => {
    expect(encodeSelection({ preset: null, added: [], removed: [] })).toBe("");
  });

  it("tidies hand-edited links: blanks, duplicates and order", () => {
    expect(decodeSelection("?add=steel,,hematite,steel&preset=")).toEqual({ preset: null, added: ["hematite", "steel"], removed: [] });
  });
});
