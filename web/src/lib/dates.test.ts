import { describe, expect, it } from "vitest";

import { retrievedOn } from "./dates";

describe("retrievedOn", () => {
  it("dates the snapshot in UTC", () => {
    expect(retrievedOn("2026-11-22T23:58:22Z")).toBe("22 Nov 2026");
    expect(retrievedOn(null)).toBe("an unknown date");
  });
});
