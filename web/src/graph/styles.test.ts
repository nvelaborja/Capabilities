import { describe, expect, it } from "vitest";

import type { DrawnKind } from "../api/types";
import { STATUS_LABELS, TYPE_LABELS } from "../legend/Legend";
import { STATUSES } from "./statuses";
import { STRIP_WIDTH } from "./elements";
import { buildStylesheet, EDGE_OPACITY, ICON_SIZE, type GraphTokens, STATUS_LOOK, TYPE_ICONS, TYPED_KINDS, type TypeColours } from "./styles";

const colours = (seed: string): TypeColours => ({ fill: `${seed}1`, ink: `${seed}2`, tint: `${seed}3`, line: `${seed}4` });
const tokens: GraphTokens = {
  surface: "#fff", nodeBg: "#fafafa", nodeText: "#000", text: "#111", muted: "#666", accent: "#06c", edge: "#999", edgeLive: "#06c", out: "#bbb",
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

  it("gives every node the same surface and text colour, with the label clear of the strip", () => {
    expect(styleOf("node")).toMatchObject({ "background-color": "#fafafa", color: "#000", "text-margin-x": STRIP_WIDTH / 2 });
  });

  it.each(TYPED_KINDS)("marks %s nodes with a strip in their colour, their emoji, and a border in their colour", (kind) => {
    const style = styleOf(`node.${kind}`);
    const [strip, icon] = style?.["background-image"] as string[];
    expect(decodeURIComponent(strip ?? "")).toContain(`fill="${tokens.types[kind].fill}"`);
    expect(decodeURIComponent(icon ?? "")).toContain(TYPE_ICONS[kind]);
    expect(style?.["border-color"]).toBe(tokens.types[kind].line);
    expect(style?.["background-width"]).toEqual([`${STRIP_WIDTH}px`, `${ICON_SIZE}px`]);
  });

  it("gives every type its own emoji", () => {
    expect(new Set(Object.values(TYPE_ICONS)).size).toBe(TYPED_KINDS.length);
  });

  it("gives every status its own border width, border style and opacity, so none relies on colour", () => {
    const looks = STATUSES.map((status) => {
      const style = styleOf(`node.status-${status}`);
      return JSON.stringify([style?.["border-width"], style?.["border-style"], style?.opacity]);
    });
    expect(new Set(looks).size).toBe(STATUSES.length);
  });

  it("never changes a node's background for its status, only its border and opacity", () => {
    for (const status of Object.keys(STATUS_LOOK)) {
      expect(styleOf(`node.status-${status}`)).not.toHaveProperty("background-color");
    }
  });

  it("keeps edges in the background until a node is clicked", () => {
    expect(styleOf("edge")?.opacity).toBe(EDGE_OPACITY.idle);
    expect(EDGE_OPACITY.faded).toBeLessThan(EDGE_OPACITY.idle);
    expect(EDGE_OPACITY.idle).toBeLessThan(EDGE_OPACITY.live);
    expect(EDGE_OPACITY.live).toBeLessThan(EDGE_OPACITY.highlighted);
    // Highlighting must come after "live", or working routes would stay dim when clicked.
    const live = sheet.findIndex((b) => b.selector === "edge.live");
    expect(sheet.findIndex((b) => b.selector === "edge.highlighted")).toBeGreaterThan(live);
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
