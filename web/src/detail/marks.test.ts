import { describe, expect, it } from "vitest";

import type { Status } from "../api/types";
import { MARKS, routeVerdict, statusTri, waysHeading } from "./marks";

describe("marks", () => {
  it("never relies on colour: each answer has its own glyph and words", () => {
    const marks = Object.values(MARKS);
    expect(new Set(marks.map((m) => m.glyph)).size).toBe(3);
    expect(new Set(marks.map((m) => m.label)).size).toBe(3);
  });

  it.each<[Status | undefined, string]>([
    ["selected", "yes"],
    ["hypothetical", "yes"],
    ["implied", "yes"],
    ["reachable", "yes"],
    ["maybe", "maybe"],
    ["near", "no"],
    ["out", "no"],
    [undefined, "no"],
  ])("treats %s as %s", (status, tri) => {
    expect(statusTri(status)).toBe(tri);
  });
});

describe("routeVerdict", () => {
  it.each([
    [{ status: "yes" as const, missing: 0, uncertain: 0 }, "Works"],
    [{ status: "no" as const, missing: 1, uncertain: 0 }, "Missing 1"],
    [{ status: "no" as const, missing: 2, uncertain: 1 }, "Missing 2 · 1 unknown"],
    [{ status: "maybe" as const, missing: 0, uncertain: 1 }, "1 unknown"],
    [{ status: "maybe" as const, missing: 0, uncertain: 0 }, "Might work"],
  ])("summarises %o as %s", (route, verdict) => {
    expect(routeVerdict(route)).toBe(verdict);
  });
});

describe("waysHeading", () => {
  it.each([
    ["artifact", "Ways to make it"],
    ["material", "Ways to make it"],
    ["effect", "Ways to reach it"],
    ["action", "Ways to do it"],
  ])("heads %s routes with %s", (kind, heading) => {
    expect(waysHeading(kind)).toBe(heading);
  });

  it("says a found material is extracted, and a source is where it comes from", () => {
    expect(waysHeading("material", "extracted")).toBe("Ways to extract it");
    expect(waysHeading("source")).toBe("Where it comes from");
  });
});
