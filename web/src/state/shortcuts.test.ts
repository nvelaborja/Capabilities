import { describe, expect, it } from "vitest";

import { historyShortcut, type KeyLike } from "./shortcuts";

const key = (overrides: Partial<KeyLike>): KeyLike => ({ key: "z", metaKey: false, ctrlKey: false, shiftKey: false, target: null, ...overrides });

describe("historyShortcut", () => {
  it.each([
    [{ metaKey: true }, "undo"],
    [{ metaKey: true, shiftKey: true, key: "Z" }, "redo"],
    [{ ctrlKey: true }, "undo"],
    [{ ctrlKey: true, key: "y" }, "redo"],
    [{}, null],
    [{ metaKey: true, key: "c" }, null],
  ] as const)("%j → %s", (overrides, expected) => {
    expect(historyShortcut(key(overrides))).toBe(expected);
  });

  it("leaves typing alone", () => {
    const input = { tagName: "INPUT" } as unknown as EventTarget;
    expect(historyShortcut(key({ metaKey: true, target: input }))).toBeNull();
  });
});
