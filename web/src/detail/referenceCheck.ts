import type { ReferenceCheck } from "../api/types";

/** A piece of a line: plain text, or a link. */
export type Segment = { text: string } | { href: string; label: string };

/**
 * What the citation check found for a work, as a line of text and links (ADR 0047). It says where the work was found,
 * never that the claim is verified: only a person reading the work changes a reference's status.
 */
export function checkSegments(check: ReferenceCheck): Segment[] {
  const record: Segment[] = check.match && isWeb(check.match.url) ? [{ href: check.match.url, label: check.match.service }] : [];
  const freeCopy: Segment[] = isWeb(check.free_copy) ? [{ text: " · " }, { href: check.free_copy, label: "free copy" }] : [];
  switch (check.result) {
    case "found":
      return [{ text: "Found in " }, ...record, ...freeCopy];
    case "review_found":
      return [{ text: "Only a review of it is in " }, ...record, ...freeCopy];
    case "possible":
      return [{ text: "Possibly in " }, ...record, ...(check.note ? [{ text: `: ${check.note}` }] : []), ...freeCopy];
    case "doi_disagrees":
      return [{ text: "The DOI leads to a different work in " }, ...record];
    case "not_found":
      return [{ text: "Not found in OpenAlex or Crossref" }];
    case "not_checked_yet":
      return [{ text: "Not looked up yet" }];
    case "not_searched":
      return [];
  }
}

/** What to say about a reference's own link, when it didn't simply load. */
export function linkStateText(state: ReferenceCheck["link"]): string | null {
  if (state === "broken") return "broken";
  if (state === "refused") return "the site refused an automated check";
  return null;
}

/** Links from upstream records are only followed when they are web addresses. */
function isWeb(url: string | undefined): url is string {
  return !!url && /^https?:\/\//i.test(url);
}
