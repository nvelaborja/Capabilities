import { describe, expect, it } from "vitest";

import type { DrawnKind } from "../api/types";
import { STATUS_LABELS, TYPE_LABELS } from "../legend/Legend";
import { STATUSES } from "./statuses";
import { buildStylesheet, type GraphTokens, STATUS_LOOK, TYPED_KINDS, type TypeColours } from "./styles";

const colours = (seed: string): TypeColours => ({ fill: `${seed}1`, ink: `${seed}2`, tint: `${seed}3`, line: `${seed}4` });
const tokens: GraphTokens = {
  surface: "#fff", text: "#111", muted: "#666", accent: "#06c", edge: "#999", edgeLive: "#06c", out: "#bbb",
  types: Object.fromEntries(TYPED_KINDS.map((kind) => [kind, colours(`#${kind}`)])) as Record<DrawnKind, TypeColours>,
};

const sheet = buildStylesheet(tokens);
const styleOf = (selector: string) => {
  const block = sheet.find((b) => b.selector === selector);
  return (block && ("style" in block ? block.style : block.css)) as Record<string, unknown> | undefined;
};

describe("graph stylesheet", () => {
  it("draws every node as a rounded rectangle, except route dots", () => {
    expect(styleOf("node")?.shape).toBe("round-rectangle");
    expect(sheet.filter((b) => b.selector !== "node.route" && b.selector !== "node.level-label" && "style" in b && "shape" in b.style)).toHaveLength(1);
  });

  it.each(TYPED_KINDS)("colours %s nodes with their own tint and border", (kind) => {
    expect(styleOf(`node.${kind}`)).toEqual({ "background-color": tokens.types[kind].tint, "border-color": tokens.types[kind].line });
  });

  it("gives every status its own border width, border style and opacity, so none relies on colour", () => {
    const looks = STATUSES.map((status) => {
      const style = styleOf(`node.status-${status}`);
      return JSON.stringify([style?.["border-width"], style?.["border-style"], style?.opacity]);
    });
    expect(new Set(looks).size).toBe(STATUSES.length);
  });

  it("fills things they had with the type's strong colour", () => {
    const hadIt = sheet.find((b) => b.selector.includes("node.material.status-implied"));
    expect(hadIt && "style" in hadIt && hadIt.style).toMatchObject({ "background-color": tokens.types.material.fill });
    expect(Object.entries(STATUS_LOOK).filter(([, look]) => look.hadIt).map(([status]) => status)).toEqual([
      "selected", "hypothetical", "implied",
    ]);
  });

  it("puts status rules after type rules so they win", () => {
    const type = sheet.findIndex((b) => b.selector === "node.material");
    const status = sheet.findIndex((b) => b.selector === "node.status-out");
    expect(status).toBeGreaterThan(type);
  });
});

describe("legend", () => {
  it("explains every status and every type the graph draws", () => {
    expect(Object.keys(STATUS_LABELS).sort()).toEqual([...STATUSES].sort());
    expect(Object.keys(TYPE_LABELS).sort()).toEqual([...TYPED_KINDS].sort());
  });
});
