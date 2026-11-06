import { describe, expect, it } from "vitest";

import { bound, LIMIT, summaryLabel } from "./bounded";

interface Item {
  id: string;
  kind: string;
}

const items = (kinds: string[]): Item[] => kinds.map((kind, index) => ({ id: `${kind}-${index}`, kind }));
const kindOf = (item: Item) => item.kind;

describe("bound", () => {
  it("shows everything, with nothing summarised, when the list fits", () => {
    const list = items(Array(LIMIT).fill("material"));
    expect(bound(list, kindOf)).toEqual({ shown: list, hidden: [] });
  });

  it("shows exactly the first N in their given order and summarises the rest by kind", () => {
    // given: ten items ranked by the caller, three over a limit of seven
    const list = items(["artifact", "material", "artifact", "material", "action", "material", "artifact", "material", "artifact", "material"]);
    // when: bounding to seven
    const { shown, hidden } = bound(list, kindOf, 7);
    // then: the first seven are shown as given, and the other three are grouped by kind in order of appearance
    expect(shown).toEqual(list.slice(0, 7));
    expect(hidden.map((group) => [group.kind, group.items.map((item) => item.id)])).toEqual([
      ["material", ["material-7", "material-9"]],
      ["artifact", ["artifact-8"]],
    ]);
  });

  it("never loses or repeats an item", () => {
    const list = items(Array.from({ length: 30 }, (_, index) => ["material", "artifact", "effect"][index % 3] ?? "material"));
    const { shown, hidden } = bound(list, kindOf);
    const all = [...shown, ...hidden.flatMap((group) => group.items)];
    expect(all).toHaveLength(list.length);
    expect(new Set(all.map((item) => item.id)).size).toBe(list.length);
  });
});

describe("summaryLabel", () => {
  it.each([
    ["material", 43, "43 other materials"],
    ["material", 1, "1 other material"],
    ["artifact", 12, "12 other tools and products"],
    ["artifact", 1, "1 other tool or product"],
    ["category", 2, "2 other classes"],
    ["route", 3, "3 other ways"],
    ["mystery", 2, "2 other items"],
  ])("names %s × %i as %s", (kind, count, label) => {
    expect(summaryLabel(kind, count)).toBe(label);
  });
});
