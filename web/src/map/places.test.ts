import { describe, expect, it } from "vitest";

import type { OccurrencesResponse, SourceSummary } from "../api/types";
import {
  bounds,
  canMap,
  classLevelText,
  attestedText,
  datingText,
  emptyReason,
  periodsText,
  placesUnder,
  recordLinkText,
  safeLink,
  sourceLine,
  stateText,
  untilText,
  whereText,
  yearText,
} from "./places";

const hematite: SourceSummary = { id: "hematite-deposit", label: "Hematite deposit", availability: "regional", regions: ["Widespread"], places: 2655, worked: 659, class_level: false };

function response(overrides: Partial<OccurrencesResponse> = {}): OccurrencesResponse {
  return {
    id: "hematite",
    label: "Hematite",
    kind: "material",
    origin: "extracted",
    sources: [hematite],
    datasets: [{ id: "mrds", label: "USGS MRDS", short: "MRDS", home: null, note: "Modern records.", retrieved_at: "2026-11-22T21:58:22Z", license: null }],
    features: {
      type: "FeatureCollection",
      features: [
        { type: "Feature", geometry: { type: "Point", coordinates: [-106.26, 39.24] }, properties: {} as never },
        { type: "Feature", geometry: { type: "Point", coordinates: [97.23, 20.75] }, properties: {} as never },
      ],
    },
    ...overrides,
  };
}

describe("canMap", () => {
  it("maps sources and the materials taken from them, not made or hand-gathered things", () => {
    expect(canMap("source")).toBe(true);
    expect(canMap("material", "extracted")).toBe(true);
    expect(canMap("material", "produced")).toBe(false);
    expect(canMap("material", "natural")).toBe(false);
    expect(canMap("artifact")).toBe(false);
  });
});

describe("sourceLine", () => {
  it("counts places and those known to have been worked", () => {
    expect(sourceLine(hematite, true)).toBe("Hematite deposit: 2,655 places, 659 known to have been worked.");
  });

  it("says a source found almost everywhere isn't mapped", () => {
    expect(sourceLine({ ...hematite, label: "Standing trees", availability: "ubiquitous", places: 0 }, true)).toBe(
      "Standing trees: found almost everywhere, so not mapped.",
    );
  });

  it("falls back to the curated regions when nothing is mapped, and says why", () => {
    const bogIron = { ...hematite, label: "Bog iron deposit", regions: ["Northern Europe"], places: 0, worked: 0 };
    expect(sourceLine(bogIron, true)).toBe("Bog iron deposit: no mapped places yet. Known regions: Northern Europe.");
    expect(sourceLine(bogIron, false)).toBe(
      "Bog iron deposit: no places, because no upstream data has been downloaded. Known regions: Northern Europe.",
    );
  });
});

describe("emptyReason", () => {
  it("is null when there are places to draw", () => {
    expect(emptyReason(response())).toBeNull();
  });

  it("explains a made thing, and a snapshot that was never downloaded", () => {
    const none = { type: "FeatureCollection" as const, features: [] };
    expect(emptyReason(response({ label: "Steel", origin: "produced", sources: [], features: none }))).toBe(
      "Steel is made, not found, so it has no places.",
    );
    expect(emptyReason(response({ datasets: [], features: none }))).toMatch(/No upstream data has been downloaded/);
  });
});

describe("place text", () => {
  it("never calls a place without a date unworked", () => {
    expect(stateText({ state: "worked", worked_by_year: 1860 })).toBe("Known to have been worked by 1860");
    expect(stateText({ state: "present", worked_by_year: null })).toBe("Present, with no known working date");
  });

  it("names where a place is from whatever is known", () => {
    expect(whereText({ admin_area: "Colorado", country: "United States" })).toBe("Colorado, United States");
    expect(whereText({ admin_area: null, country: "Burma" })).toBe("Burma");
    expect(whereText({ admin_area: null, country: null })).toBe("Location name unknown");
  });
});

describe("bounds", () => {
  const at = (longitude: number, latitude: number) => ({
    type: "Feature" as const,
    geometry: { type: "Point" as const, coordinates: [longitude, latitude] as [number, number] },
    properties: {} as never,
  });

  it("is the box around every place, west, south, east, north", () => {
    const places = response({ features: { type: "FeatureCollection", features: [at(-106.26, 39.24), at(-66.38, -22.63)] } });
    expect(bounds(places)).toEqual([-106.26, -22.63, -66.38, 39.24]);
  });

  it("is null with no places, or places spread over more than half the globe", () => {
    expect(bounds(response({ features: { type: "FeatureCollection", features: [] } }))).toBeNull();
    expect(bounds(response())).toBeNull(); // Colorado and Burma
  });
});

describe("popup links", () => {
  it("follows only http and https links from a dataset", () => {
    expect(safeLink("https://mrdata.usgs.gov/mrds/show-mrds.php?dep_id=10008106")).toBe(
      "https://mrdata.usgs.gov/mrds/show-mrds.php?dep_id=10008106",
    );
    expect(safeLink("http://example.org/a")).toBe("http://example.org/a");
    expect(safeLink("javascript:alert(1)")).toBeNull();
    expect(safeLink("data:text/html,<b>hi</b>")).toBeNull();
    expect(safeLink("not a url")).toBeNull();
    expect(safeLink(null)).toBeNull();
  });

  it("names the dataset the record is in", () => {
    const { datasets } = response();
    expect(recordLinkText("mrds", datasets)).toBe("Its record in MRDS ↗");
    expect(recordLinkText("pleiades", datasets)).toBe("Its record in pleiades ↗");
  });
});

describe("placesUnder", () => {
  const place = (id: string, name: string | null) => ({ properties: { id, name } });

  it("lists every place under a click once, by name", () => {
    const under = placesUnder([place("b", "Tilt Cove"), place("a", "Betts Cove"), place("b", "Tilt Cove"), place("c", null)]);
    expect(under.map((feature) => feature.properties.id)).toEqual(["c", "a", "b"]);
  });
});

describe("working dates (ADR 0051)", () => {
  const undated = {
    worked_by_year: null,
    worked_by_note: null,
    worked_by_references: null,
    worked_by_period_end: null,
    upstream_worked_by_year: null,
    upstream_worked_by_note: null,
  };

  it("writes years as historians do: BC, AD before 1000, and plain after", () => {
    expect([yearText(-2500), yearText(1), yearText(999), yearText(1860)]).toEqual(["2500 BC", "AD 1", "AD 999", "1860"]);
    expect(stateText({ state: "worked", worked_by_year: -550 })).toBe("Known to have been worked by 550 BC");
  });

  it("says where a year came from", () => {
    expect(datingText({ ...undated, worked_by_basis: "first production" })).toBe("From its first production, as MRDS records it");
    const archaic = { worked_by_year: -550, worked_by_note: "Archaic (Greco-Roman; 750-550 BCE/BC)", worked_by_period_end: -550 };
    expect(datingText({ ...undated, ...archaic, worked_by_basis: "period" })).toBe(
      "Attested in Archaic (Greco-Roman; 750-550 BCE/BC), which had ended by then",
    );
    expect(datingText({ ...undated, worked_by_basis: null })).toBeNull();
  });

  it("never says a period had ended when it was still running when the data was taken", () => {
    // given: a place attested only in the Modern period, which Pleiades runs to 2100, dated by the snapshot's year
    const modern = { worked_by_year: 2026, worked_by_note: "Modern (AD 1700-Present)", worked_by_period_end: 2100 };
    expect(datingText({ ...undated, ...modern, worked_by_basis: "period" })).toBe(
      "Attested in Modern (AD 1700-Present), which hadn't ended when the data was taken",
    );
  });

  it("gives a dated place's attested years beside its year, and leaves them to the state for an undated one", () => {
    expect(attestedText({ worked_by_year: -550, attested_from: -750, attested_to: 300 })).toBe("Attested 750 BC – AD 300");
    expect(attestedText({ worked_by_year: null, attested_from: -750, attested_to: 300 })).toBeNull();
    expect(attestedText({ worked_by_year: 1860, attested_from: null, attested_to: null })).toBeNull();
  });

  it("gives a curated date's reason and citations, and what the dataset said, as the API or MapLibre hands them", () => {
    const references = [{ citation: "Test, A. (2026). A work.", status: "unverified" }];
    // given: a reason written as a sentence, replacing the year Pleiades' Archaic period gave
    const curated = {
      ...undated,
      worked_by_year: -1200,
      worked_by_basis: "curated" as const,
      worked_by_note: "Slag dated to 1200 BC.",
      upstream_worked_by_year: -550,
      upstream_worked_by_note: "Archaic (Greco-Roman; 750-550 BCE/BC)",
    };
    const expected =
      "Curated date: Slag dated to 1200 BC (Test, A. (2026). A work.). The dataset says 550 BC, from Archaic (Greco-Roman; 750-550 BCE/BC).";
    expect(datingText({ ...curated, worked_by_references: references })).toBe(expected);
    expect(datingText({ ...curated, worked_by_references: JSON.stringify(references) })).toBe(expected);
    expect(datingText({ ...curated, worked_by_references: null, upstream_worked_by_year: null })).toBe(
      "Curated date: Slag dated to 1200 BC.",
    );
    expect(datingText({ ...curated, worked_by_references: null, upstream_worked_by_year: 1860, upstream_worked_by_note: null })).toBe(
      "Curated date: Slag dated to 1200 BC. The dataset says 1860.",
    );
  });
});

describe("Pleiades places (ADR 0046)", () => {
  it("says a working was worked, with the years it is attested, BC and AD", () => {
    const place = { state: "worked" as const, worked_by_year: null, attested_from: -330, attested_to: 640 };
    expect(stateText(place)).toBe("Worked: attested 330 BC – AD 640");
    expect([yearText(-750), yearText(300)]).toEqual(["750 BC", "AD 300"]);
    expect(stateText({ state: "worked", worked_by_year: null, attested_from: null, attested_to: null })).toBe(
      "Worked, with no recorded dates",
    );
  });

  it("says a range that runs into Pleiades' modern periods runs to the present, never to a year to come", () => {
    expect(untilText(2100, 2026)).toBe("the present");
    expect([untilText(2026, 2026), untilText(1999, 2026)]).toEqual(["2026", "1999"]);
  });

  it("names the periods in words, whether the API's list or MapLibre's JSON string", () => {
    const expected = "Periods: Hellenistic republican, Roman";
    expect(periodsText(["hellenistic-republican", "roman"])).toBe(expected);
    expect(periodsText('["hellenistic-republican","roman"]')).toBe(expected);
    expect([periodsText(null), periodsText([]), periodsText("not json")]).toEqual([null, null, null]);
  });

  it("says which ore a class-level place had isn't recorded, in the popup and the summary", () => {
    expect(classLevelText("Copper ore")).toBe("Copper ore mined here; which ore isn't recorded");
    const copper: SourceSummary = { id: "copper-ore", label: "Copper ore", regions: [], places: 118, worked: 118, class_level: true };
    expect(sourceLine(copper, true)).toBe("Copper ore, which ore isn't recorded: 118 ancient mines.");
  });
});
