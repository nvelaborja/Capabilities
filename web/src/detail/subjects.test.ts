import { describe, expect, it } from "vitest";

import { edgeSubject, parseSubject } from "./subjects";

describe("detail subjects", () => {
  it("round-trips a line, including actions whose ids contain a colon", () => {
    expect(parseSubject(edgeSubject("cut:wood", "steel-spear"))).toEqual({ type: "edge", source: "cut:wood", target: "steel-spear" });
  });

  it("reads anything else as a node, including actions", () => {
    expect(parseSubject("cut:granite")).toEqual({ type: "node", id: "cut:granite" });
  });
});
