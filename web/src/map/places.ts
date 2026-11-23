import type { OccurrencesResponse, PlaceProperties, SourceSummary } from "../api/types";

/** Whether a node can be shown on the map: a source, or a material taken from one (ADR 0032). */
export function canMap(kind: string, origin?: string | null): boolean {
  return kind === "source" || (kind === "material" && origin === "extracted");
}

const count = (n: number, one: string, many: string) => `${n.toLocaleString("en")} ${n === 1 ? one : many}`;

/** One line per source: how many places are mapped and how many are known to have been worked, or why there are none. */
export function sourceLine(source: SourceSummary, haveData: boolean): string {
  if (source.availability === "ubiquitous") return `${source.label}: found almost everywhere, so not mapped.`;
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

/** "22 Nov 2026" from an ISO time, in UTC so it matches the manifest. */
export function retrievedOn(iso: string | null): string {
  if (!iso) return "an unknown date";
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

/** What the popup says about a place's state: never "not worked", only "no known working date" (ADR 0041). */
export function stateText(place: Pick<PlaceProperties, "state" | "worked_by_year">): string {
  return place.state === "worked" && place.worked_by_year !== null
    ? `Known to have been worked by ${place.worked_by_year}`
    : "Present, with no known working date";
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
