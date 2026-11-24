import { describe, expect, it } from "vitest";

import type { QuantitySource } from "../api/types";
import { nodeOrigin, sourceLines } from "./provenance";

const upstream = {
  dataset: "Wikidata",
  record: "Q41177",
  url: "https://www.wikidata.org/wiki/Q41177",
  retrieved_at: "2026-11-24T00:14:22Z",
  value: "5–7 Mohs",
};
const record = { href: "https://www.wikidata.org/wiki/Q41177", label: "Wikidata Q41177" };

describe("sourceLines", () => {
  it("names the upstream record and when it was retrieved", () => {
    expect(sourceLines({ layer: "upstream", upstream }, false)).toEqual([{ text: "From Wikidata, retrieved 24 Nov 2026:", link: record }]);
  });

  it("keeps a curated value that disagrees in view", () => {
    const lines = sourceLines({ layer: "upstream", upstream, curated_value: "6–7 Mohs" }, false);
    expect(lines.map((line) => line.text)).toContain("Our curated value was 6–7 Mohs.");
  });

  it("shows what an override replaces and why, and when it needs review", () => {
    const source: QuantitySource = {
      layer: "override",
      upstream,
      override: {
        reason: "Quartz and feldspar are 6 to 7.",
        replaces: "5–7 Mohs",
        references: [{ citation: "Klein & Dutrow (2007).", status: "unverified" }],
        stale: false,
      },
    };
    expect(sourceLines(source, false)).toEqual([
      { text: "Overridden. Wikidata says 5–7 Mohs:", link: record },
      { text: "Quartz and feldspar are 6 to 7." },
      { text: "Source: Klein & Dutrow (2007)." },
    ]);
    const stale = { ...source, override: { ...source.override!, stale: true } };
    expect(sourceLines(stale, false).at(-1)?.text).toMatch(/needs review/);
  });

  it("points a curated value at the sources, and says when there are none", () => {
    expect(sourceLines({ layer: "curated" }, true)).toEqual([{ text: "Curated: see the sources below." }]);
    expect(sourceLines({ layer: "curated" }, false)).toEqual([{ text: "Curated, with no source yet." }]);
  });
});

describe("nodeOrigin", () => {
  const crosswalk = "data/crosswalks/ore_minerals.csv";

  it("links a mineral to its Wikidata item", () => {
    const upstream = { crosswalk, dataset: "Wikidata", record: "Q108212", url: "https://www.wikidata.org/wiki/Q108212" };
    expect(nodeOrigin(upstream)).toEqual({
      text: "From Wikidata",
      link: { href: "https://www.wikidata.org/wiki/Q108212", label: "Q108212" },
    });
  });

  it("names the records a deposit's places come from when there is no single record to open", () => {
    const upstream = { crosswalk, dataset: "MRDS", record: "deposits listing Azurite as an ore mineral" };
    expect(nodeOrigin(upstream)).toEqual({ text: "From MRDS (deposits listing Azurite as an ore mineral)" });
  });

  it("names the route a mining route copies", () => {
    const upstream = { crosswalk, copied_from: { id: "mine-malachite", label: "Mining malachite with stone hammers" } };
    expect(nodeOrigin(upstream)).toEqual({ text: "A copy of Mining malachite with stone hammers" });
  });
});
