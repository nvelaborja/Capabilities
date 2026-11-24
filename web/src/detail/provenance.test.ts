import { describe, expect, it } from "vitest";

import type { QuantitySource } from "../api/types";
import { sourceLines } from "./provenance";

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
    expect(sourceLines({ layer: "upstream", upstream })).toEqual([{ text: "From Wikidata, retrieved 24 Nov 2026:", link: record }]);
  });

  it("keeps a curated value that disagrees in view", () => {
    const lines = sourceLines({ layer: "upstream", upstream, curated_value: "6–7 Mohs" });
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
    expect(sourceLines(source)).toEqual([
      { text: "Overridden. Wikidata says 5–7 Mohs:", link: record },
      { text: "Quartz and feldspar are 6 to 7." },
      { text: "Source: Klein & Dutrow (2007)." },
    ]);
    const stale = { ...source, override: { ...source.override!, stale: true } };
    expect(sourceLines(stale).at(-1)?.text).toMatch(/needs review/);
  });

  it("points a curated value at the sources", () => {
    expect(sourceLines({ layer: "curated" })).toEqual([{ text: "Curated: see the sources below." }]);
  });
});
