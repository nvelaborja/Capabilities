import { describe, expect, it } from "vitest";

import { chipStatus } from "./marks";
import { lineStyle } from "./lines";

describe("lineStyle", () => {
  it.each([
    [["consumed"], "Solid line", "used up"],
    [["tool"], "Dashed line", "not used up"],
    [["action"], "Dotted line", "action"],
    [["effect"], "Solid line with a label", "threshold"],
  ] as const)("explains %s lines", (roles, look, meaning) => {
    const style = lineStyle("requires", roles, false);
    expect(style.look).toBe(look);
    expect(style.meaning).toContain(meaning);
  });

  it("explains merged lines, byproducts and is-a links", () => {
    expect(lineStyle("requires", ["consumed", "tool"], false)).toEqual({
      look: "Solid line",
      meaning: "used in more than one way (an ingredient; a tool)",
    });
    expect(lineStyle("requires", ["consumed"], true).meaning).toContain("byproduct");
    expect(lineStyle("is_a", [], false).look).toBe("Thin dashed line, no arrow");
  });
});

describe("chipStatus", () => {
  it("uses the selection's status when there is one, else the answer", () => {
    expect(chipStatus("implied", "maybe")).toBe("implied");
    expect(chipStatus(undefined, "yes")).toBe("reachable");
    expect(chipStatus(undefined, "maybe")).toBe("maybe");
    expect(chipStatus(undefined, "no")).toBe("out");
  });
});
