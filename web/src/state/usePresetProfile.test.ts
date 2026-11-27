import { describe, expect, it } from "vitest";

import type { ProfileDetail } from "../api/types";
import { presetItemIds } from "./usePresetProfile";

describe("a preset's items", () => {
  it("are its list and the sources the map added, so removing either is an edit", () => {
    const profile: ProfileDetail = {
      id: "p",
      label: "P",
      includes: [{ id: "copper" }, { verb: "cut", target: "granite" }],
      map: {
        cliopatria: "X",
        years: [-600, -531],
        cliopatria_years: [-600, -531],
        cliopatria_rows: 1,
        wikidata: null,
        release: "v0.2.2",
        sources: [
          { id: "granite-outcrop", label: "Granite outcrop", kind: "source", availability: "yes", worked_by_then: 1, not_known_worked: 0, listed: false, from_map: true },
          { id: "limestone-outcrop", label: "Limestone outcrop", kind: "source", availability: "maybe", worked_by_then: 0, not_known_worked: 2, listed: false, from_map: false },
        ],
      },
    };
    expect([...presetItemIds(profile)].sort()).toEqual(["copper", "cut:granite", "granite-outcrop"]);
    expect([...presetItemIds({ ...profile, map: null })].sort()).toEqual(["copper", "cut:granite"]);
  });
});
