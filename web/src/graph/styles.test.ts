import { describe, expect, it } from "vitest";

import { SHAPES, STATUS_STYLES } from "../legend/Legend";
import { STATUSES } from "./statuses";
import { buildStylesheet, type GraphTokens } from "./styles";

const tokens: GraphTokens = {
  surface: "#fff", text: "#111", muted: "#666", border: "#ccc", accent: "#06c", accentStrong: "#036",
  accentTint: "#def", onAccent: "#fff", whatIf: "#a60", edge: "#999", edgeLive: "#06c", out: "#bbb",
};

const sheet = buildStylesheet(tokens);
const styleFor = (selector: string) => {
  const block = sheet.find((b) => b.selector === selector);
  return block && ("style" in block ? block.style : block.css);
};

describe("graph stylesheet", () => {
  it.each(STATUSES)("styles the %s status with more than colour", (status) => {
    // Status must never depend on colour alone (design doc), so each rule sets a border, fill pattern or opacity.
    const style = styleFor(`node.status-${status}`) as Record<string, unknown> | undefined;
    expect(style).toBeDefined();
    const nonColour = ["border-width", "border-style", "opacity"].filter((key) => style && key in style);
    expect(nonColour.length).toBeGreaterThan(0);
  });

  it.each(["material", "artifact", "action", "category", "effect"])("gives %s nodes a shape", (kind) => {
    expect(styleFor(`node.${kind}`)).toHaveProperty("shape");
  });

  it("puts status rules after the base rules so they win", () => {
    const base = sheet.findIndex((b) => b.selector === "node.material");
    const status = sheet.findIndex((b) => b.selector === "node.status-selected");
    expect(status).toBeGreaterThan(base);
  });
});

describe("legend", () => {
  it("explains every status and every shape the graph draws", () => {
    expect(Object.keys(STATUS_STYLES).sort()).toEqual([...STATUSES].sort());
    expect(Object.keys(SHAPES).sort()).toEqual(["action", "artifact", "category", "effect", "material", "route"]);
  });
});
