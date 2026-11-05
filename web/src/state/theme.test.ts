import { describe, expect, it } from "vitest";

import { applyPreference, resolveTheme } from "./theme";

describe("resolveTheme", () => {
  it.each([
    ["system", true, "dark"],
    ["system", false, "light"],
    ["light", true, "light"],
    ["dark", false, "dark"],
  ] as const)("%s with a dark system = %s gives %s", (preference, systemIsDark, theme) => {
    expect(resolveTheme(preference, systemIsDark)).toBe(theme);
  });
});

describe("applyPreference", () => {
  it("sets data-theme for an explicit choice and removes it for the system theme", () => {
    const root = { dataset: {} as DOMStringMap } as HTMLElement;
    applyPreference("dark", root);
    expect(root.dataset.theme).toBe("dark");
    applyPreference("system", root);
    expect(root.dataset.theme).toBeUndefined();
  });
});
