import { describe, expect, it } from "vitest";

import type { ReferenceCheck } from "../api/types";
import { checkSegments, linkStateText } from "./referenceCheck";

const match = { service: "OpenAlex", url: "https://openalex.org/W1", title: "Sliding Friction on Wet and Dry Sand", year: 2014 };
const check = (fields: Partial<ReferenceCheck>): ReferenceCheck => ({ result: "found", checked_at: "2026-11-24T21:45:44Z", ...fields });

describe("checkSegments", () => {
  it("links the record found, and a free copy when there is one", () => {
    expect(checkSegments(check({ match, free_copy: "https://example.org/w1.pdf" }))).toEqual([
      { text: "Found in " },
      { href: "https://openalex.org/W1", label: "OpenAlex" },
      { text: " · " },
      { href: "https://example.org/w1.pdf", label: "free copy" },
    ]);
  });

  it("says when only a review of the work was found", () => {
    expect(checkSegments(check({ result: "review_found", match }))[0]).toEqual({ text: "Only a review of it is in " });
  });

  it("says why a match is only possible", () => {
    const segments = checkSegments(check({ result: "possible", match, note: "the year differs (cited 1992, found 1978)" }));
    expect(segments).toContainEqual({ text: ": the year differs (cited 1992, found 1978)" });
  });

  it("says plainly when nothing was found, without calling the work doubtful", () => {
    expect(checkSegments(check({ result: "not_found" }))).toEqual([{ text: "Not found in OpenAlex or Crossref" }]);
  });

  it("never links anything but a web address", () => {
    expect(checkSegments(check({ match: { ...match, url: "javascript:alert(1)" }, free_copy: "data:text/html,x" }))).toEqual([
      { text: "Found in " },
    ]);
  });

  it("says nothing about searching for a web page", () => {
    expect(checkSegments(check({ result: "not_searched" }))).toEqual([]);
  });
});

describe("linkStateText", () => {
  it.each([
    ["works", null],
    ["broken", "broken"],
    ["refused", "the site refused an automated check"],
    [undefined, null],
  ] as const)("a link that %s", (state, text) => {
    expect(linkStateText(state)).toBe(text);
  });
});
