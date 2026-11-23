import { describe, expect, it } from "vitest";

import type { OccurrencesResponse, SourceSummary } from "../api/types";
import {
  bounds,
  canMap,
  emptyReason,
  placesUnder,
  recordLinkText,
  retrievedOn,
  safeLink,
  sourceLine,
  stateText,
  whereText,
} from "./places";

const hematite: SourceSummary = { id: "hematite-deposit", label: "Hematite deposit", availability: "regional", regions: ["Widespread"], places: 2655, worked: 659 };

function response(overrides: Partial<OccurrencesResponse> = {}): OccurrencesResponse {
  return {
    id: "hematite",
    label: "Hematite",
    kind: "material",
    origin: "extracted",
    sources: [hematite],
    datasets: [{ id: "mrds", label: "USGS MRDS", short: "MRDS", home: null, retrieved_at: "2026-11-22T21:58:22Z", license: null }],
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

  it("dates the snapshot in UTC", () => {
    expect(retrievedOn("2026-11-22T23:58:22Z")).toBe("22 Nov 2026");
    expect(retrievedOn(null)).toBe("an unknown date");
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
