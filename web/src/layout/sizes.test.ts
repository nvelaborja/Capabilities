import { describe, expect, it } from "vitest";

import { BIG_STEP, boundsFor, clampSize, dragResize, keyResize, STEP } from "./sizes";

const bounds = { min: 200, max: 600 };

describe("bounds", () => {
  it("always leaves the graph room beside the side pane", () => {
    expect(boundsFor("side", { width: 1400, height: 900 })).toEqual({ min: 240, max: 1080 });
  });

  it("never lets the maximum fall below the minimum on a tiny window", () => {
    const { min, max } = boundsFor("detail", { width: 400, height: 200 });
    expect(max).toBe(min);
  });

  it("clamps sizes into range and rounds them to whole pixels", () => {
    expect([clampSize(50, bounds), clampSize(900, bounds), clampSize(321.6, bounds)]).toEqual([200, 600, 322]);
  });
});

describe("dragging", () => {
  it("grows the side pane as the gap moves left, towards the graph", () => {
    expect(dragResize({ pointer: 1000, size: 300 }, 900, bounds)).toBe(400);
  });

  it("shrinks the detail pane as the gap moves down", () => {
    expect(dragResize({ pointer: 500, size: 300 }, 550, bounds)).toBe(250);
  });

  it("stops at the bounds", () => {
    expect(dragResize({ pointer: 1000, size: 300 }, 0, bounds)).toBe(600);
  });
});

describe("keyboard", () => {
  it.each([
    ["side", "ArrowLeft", false, 300 + STEP],
    ["side", "ArrowRight", false, 300 - STEP],
    ["side", "ArrowLeft", true, 300 + BIG_STEP],
    ["detail", "ArrowUp", false, 300 + STEP],
    ["detail", "ArrowDown", true, 300 - BIG_STEP],
    ["side", "Home", false, 200],
    ["detail", "End", false, 600],
  ] as const)("resizes the %s pane with %s (shift: %s)", (pane, key, shift, expected) => {
    expect(keyResize(pane, key, shift, 300, bounds)).toBe(expected);
  });

  it("ignores keys across the gap, so up and down don't move a side-by-side split", () => {
    expect(keyResize("side", "ArrowUp", false, 300, bounds)).toBeNull();
    expect(keyResize("detail", "ArrowLeft", false, 300, bounds)).toBeNull();
  });
});
