import type { OccurrencesResponse, PlaceProperties, SourceSummary } from "../api/types";

/** Whether a node can be shown on the map: a source, or a material taken from one (ADR 0032). */
export function canMap(kind: string, origin?: string | null): boolean {
  return kind === "source" || (kind === "material" && origin === "extracted");
}

const count = (n: number, one: string, many: string) => `${n.toLocaleString("en")} ${n === 1 ? one : many}`;

/** One line per source: how many places are mapped and how many are known to have been worked, or why there are none. */
export function sourceLine(source: SourceSummary, haveData: boolean): string {
  if (source.availability === "ubiquitous") return `${source.label}: found almost everywhere, so not mapped.`;
  if (source.class_level) {
    return `${source.label}, which ore isn't recorded: ${count(source.places, "ancient mine", "ancient mines")}.`;
  }
  if (source.places > 0) {
    return `${source.label}: ${count(source.places, "place", "places")}, ${source.worked.toLocaleString("en")} known to have been worked.`;
  }
  const regions = source.regions.length > 0 ? ` Known regions: ${source.regions.join("; ")}.` : "";
  if (!haveData) return `${source.label}: no places, because no upstream data has been downloaded.${regions}`;
  return `${source.label}: no mapped places yet.${regions}`;
}

/** Why nothing is drawn, when nothing is; null when there are places. */
export function emptyReason(places: OccurrencesResponse): string | null {
  if (places.features.features.length > 0) return null;
  if (places.sources.length === 0) {
    return places.origin === "produced"
      ? `${places.label} is made, not found, so it has no places.`
      : `${places.label} is gathered by hand where it lies; no source is recorded for it.`;
  }
  if (places.datasets.length === 0) {
    return "No upstream data has been downloaded yet. Run `cd pipeline && uv run dg launch --assets 'upstream/mrds_deposits'`, then restart the server.";
  }
  return null;
}

/** What the popup says about a place's state: never "not worked", only "no known working date" (ADR 0041). */
export function stateText(
  place: Pick<PlaceProperties, "state" | "worked_by_year"> & Partial<Pick<PlaceProperties, "attested_from" | "attested_to">>,
): string {
  if (place.state === "worked" && place.worked_by_year !== null) return `Known to have been worked by ${place.worked_by_year}`;
  if (place.state === "worked" && place.attested_from != null && place.attested_to != null) {
    return `Worked in antiquity: attested ${yearText(place.attested_from)} – ${yearText(place.attested_to)}`;
  }
  if (place.state === "worked") return "Worked in antiquity";
  return "Present, with no known working date";
}

/** A year as historians write it: 330 BC, AD 640. Negative years are BC; there is no year zero. */
export function yearText(year: number): string {
  return year < 0 ? `${-year} BC` : `AD ${year}`;
}

/** Pleiades' periods in words, "Hellenistic republican, Roman, Late antique"; null when there are none. */
export function periodsText(periods: PlaceProperties["periods"]): string | null {
  const keys = typeof periods === "string" ? parsePeriods(periods) : (periods ?? []);
  if (keys.length === 0) return null;
  const words = keys.map((key) => key.replaceAll("-", " ")).map((text) => text.charAt(0).toUpperCase() + text.slice(1));
  return `Periods: ${words.join(", ")}`;
}

function parsePeriods(text: string): string[] {
  try {
    const parsed: unknown = JSON.parse(text);
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

/** The popup's note on a place of an ore class: "Copper ore mined here; which ore isn't recorded". */
export function classLevelText(sourceLabel: string): string {
  return `${sourceLabel} mined here; which ore isn't recorded`;
}

/** Where a place is, as "Colorado, United States". */
export function whereText(place: Pick<PlaceProperties, "admin_area" | "country">): string {
  return [place.admin_area, place.country].filter(Boolean).join(", ") || "Location name unknown";
}

/**
 * The bounding box of every place, [west, south, east, north], to fit the map to. Null when there are none, or when they
 * span more than half the globe's longitudes: fitting those gives an oddly centred map, and a world view shows them better.
 */
export function bounds(places: OccurrencesResponse): [number, number, number, number] | null {
  const points = places.features.features.map((feature) => feature.geometry.coordinates);
  if (points.length === 0) return null;
  const longitudes = points.map(([longitude]) => longitude);
  const latitudes = points.map(([, latitude]) => latitude);
  const [west, east] = [Math.min(...longitudes), Math.max(...longitudes)];
  if (east - west > 180) return null;
  return [west, Math.min(...latitudes), east, Math.max(...latitudes)];
}

/** A link to follow from a popup, or null: only http and https, since the address comes from a dataset we don't control. */
export function safeLink(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : null;
  } catch {
    return null;
  }
}

/** The text of a place's link to its upstream record, naming the dataset it came from. */
export function recordLinkText(datasetId: string, datasets: OccurrencesResponse["datasets"]): string {
  const dataset = datasets.find((candidate) => candidate.id === datasetId);
  return `Its record in ${dataset?.short ?? datasetId} ↗`;
}

/**
 * The places under a click, each once and by name. Several places can share a spot (MRDS often records deposits of one
 * district at the same coordinates), and a place can come back twice when it sits on a tile edge.
 */
export function placesUnder<T extends { properties: Record<string, unknown> }>(features: T[]): T[] {
  const name = (feature: T) => String(feature.properties.name ?? "");
  const unique = new Map(features.map((feature) => [feature.properties.id, feature]));
  return [...unique.values()].sort((a, b) => name(a).localeCompare(name(b)));
}
