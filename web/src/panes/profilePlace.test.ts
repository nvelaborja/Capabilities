import { describe, expect, it } from "vitest";

import type { ProfileMap, ProfileSource } from "../api/types";
import { bordersLine, countsLine, placeLine, sourceNote, sourcesByAvailability, sourceTitle } from "./profilePlace";

const source = (overrides: Partial<ProfileSource>): ProfileSource => ({
  id: "granite-outcrop",
  label: "Granite outcrop",
  kind: "source",
  availability: "maybe",
  worked_by_then: 0,
  not_known_worked: 1,
  listed: false,
  from_map: false,
  ...overrides,
});

const place: ProfileMap = {
  cliopatria: "Middle Kingdom of Egypt",
  years: [-2050, -1650],
  cliopatria_years: [-2000, -1601],
  cliopatria_rows: 2,
  wikidata: "Q191324",
  release: "v0.2.2",
  sources: [source({ id: "a", availability: "yes", worked_by_then: 3, not_known_worked: 0 }), source({ id: "b" })],
};

describe("a preset's place (ADR 0052)", () => {
  it("says where and when, and whose borders, with years as historians write them", () => {
    expect(placeLine(place)).toBe("Middle Kingdom of Egypt, 2050 BC to 1650 BC");
    expect(bordersLine(place)).toBe("Borders from Cliopatria v0.2.2: 2 maps, 2000 BC to 1601 BC.");
    expect(bordersLine({ ...place, release: null, cliopatria_rows: 1 })).toBe("Borders from Cliopatria: 1 map, 2000 BC to 1601 BC.");
  });

  it("says in words whether each source was had or is a maybe, never by its border alone", () => {
    expect(sourceNote(source({ availability: "yes", worked_by_then: 1 }), -1650)).toBe("had: 1 place worked by 1650 BC");
    expect(sourceNote(source({ not_known_worked: 26 }), -1650)).toBe("maybe: 26 places, none known worked by then");
  });

  it("explains an ore class, which the map can't add, and a source the map added", () => {
    expect(sourceTitle(source({ kind: "category", availability: "yes" }))).toMatch(/doesn't say which ore|don't say which ore/);
    expect(sourceTitle(source({ availability: "yes", from_map: true }))).toMatch(/Added to the selection by the map/);
    expect(sourceTitle(source({ listed: true }))).toBe("Also in the preset's own list.");
    expect(sourceTitle(source({}))).toMatch(/not known to be worked by then/);
  });

  it("sums up what was found for the folded summary", () => {
    expect(countsLine(place)).toBe("1 had, 1 maybe");
    expect(countsLine({ ...place, sources: [] })).toBe("nothing found in the area");
  });

  it("puts the sources had before the maybes", () => {
    const { had, maybe } = sourcesByAvailability(place);
    expect([had.map((s) => s.id), maybe.map((s) => s.id)]).toEqual([["a"], ["b"]]);
  });
});
