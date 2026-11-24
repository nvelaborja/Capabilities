import type { QuantitySource } from "../api/types";
import { retrievedOn } from "../map/places";

/** One line of where a value came from; `link` names the upstream record to open. */
export interface SourceLine {
  text: string;
  link?: { href: string; label: string };
}

/**
 * Where a quantity value came from, in words (ADR 0034, ADR 0043). An override always shows the value it replaces and
 * why; an upstream value names its record, and the curated value when that differs.
 */
export function sourceLines(source: QuantitySource): SourceLine[] {
  const upstream = source.upstream;
  const record = upstream && { href: upstream.url, label: `${upstream.dataset} ${upstream.record}` };
  if (source.layer === "override" && source.override) {
    const lines: SourceLine[] = [
      { text: `Overridden. ${upstream?.dataset ?? "Upstream"} says ${source.override.replaces}:`, link: record },
      { text: source.override.reason },
      ...source.override.references.map((reference) => ({ text: `Source: ${reference.citation}` })),
    ];
    if (source.override.stale) lines.push({ text: "Upstream has changed since this override was written; it needs review." });
    return lines;
  }
  if (source.layer === "upstream" && upstream) {
    const lines: SourceLine[] = [{ text: `From ${upstream.dataset}, retrieved ${retrievedOn(upstream.retrieved_at)}:`, link: record }];
    if (source.curated_value) lines.push({ text: `Our curated value was ${source.curated_value}.` });
    return lines;
  }
  return [{ text: "Curated: see the sources below." }];
}
