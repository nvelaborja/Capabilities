import { describe, expect, it } from "vitest";

import { sampleGraph } from "../test/sampleGraph";
import { search, type SearchEntry, searchIndex } from "./match";

const entry = (label: string, kind = "material"): SearchEntry => ({ id: label.toLowerCase(), label, kind, drawn: true });

describe("searchIndex", () => {
  it("holds every drawn thing and action, plus actions not drawn yet, without route junctions", () => {
    const index = searchIndex(sampleGraph);
    const ids = index.map((e) => e.id);
    expect(ids).not.toContain("knap");
    expect(ids.filter((id) => id === "cut:wood")).toHaveLength(1);
    expect(index.find((e) => e.id === "cut:flint")).toEqual({ id: "cut:flint", label: "Cut flint", kind: "action", drawn: false });
    expect(index.find((e) => e.id === "cut:wood")?.drawn).toBe(true);
  });
});

describe("search", () => {
  const entries = [entry("Granite"), entry("Cut granite", "action"), entry("Copper"), entry("Copper chisel", "artifact"), entry("Tin bronze")];

  it("matches the start of each word typed, in any order", () => {
    expect(search(entries, "gra cut").map((e) => e.label)).toEqual(["Cut granite"]);
    expect(search(entries, "bron").map((e) => e.label)).toEqual(["Tin bronze"]);
    expect(search(entries, "ranite")).toEqual([]);
  });

  it("puts an exact name first, then names starting with the query, then shorter names", () => {
    // given: "granite" is a whole label, a label start and part of an action
    expect(search(entries, "granite").map((e) => e.label)).toEqual(["Granite", "Cut granite"]);
    // and: "copper" starts two labels; the shorter (exact) one comes first
    expect(search(entries, "COPPER").map((e) => e.label)).toEqual(["Copper", "Copper chisel"]);
  });

  it("returns nothing for an empty query and caps the results", () => {
    expect(search(entries, "   ")).toEqual([]);
    expect(search(entries, "c", 2)).toHaveLength(2);
  });
});
