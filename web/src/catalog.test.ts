import { describe, expect, it } from "vitest";

import { createCatalog } from "./catalog";
import { sampleGraph } from "./test/sampleGraph";

describe("catalog", () => {
  const catalog = createCatalog({ ...sampleGraph, techniques: [{ id: "knapping", label: "Knapping" }] });

  it("labels drawn nodes, techniques, and actions that aren't drawn", () => {
    expect(catalog.get("knife")).toEqual({ label: "Knife", kind: "artifact" });
    expect(catalog.get("knapping")).toEqual({ label: "Knapping", kind: "technique" });
    expect(catalog.get("cut:flint")).toEqual({ label: "Cut flint", kind: "action" });
    expect(catalog.get("cut:(any)").label).toBe("Cut anything");
  });

  it("falls back to the id for unknown items", () => {
    expect(catalog.get("unobtainium").label).toBe("unobtainium");
  });
});
