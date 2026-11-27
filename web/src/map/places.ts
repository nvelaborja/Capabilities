import type { AreaGeometry, OccurrencesResponse, PlaceProperties, SourceSummary, WorkingDateReference } from "../api/types";

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
  if (place.state === "worked" && place.worked_by_year !== null) return `Known to have been worked by ${yearText(place.worked_by_year)}`;
  // Pleiades: worked when it is attested, which may be modern only. Such a place still shows the material was there.
  if (place.state === "worked" && place.attested_from != null && place.attested_to != null) {
    return `Worked: attested ${attestedRange(place.attested_from, place.attested_to)}`;
  }
  if (place.state === "worked") return "Worked, with no recorded dates";
  return "Present, with no known working date";
}

/** A year as historians write it: 330 BC, AD 640, 1860. Negative years are BC; there is no year zero (ADR 0051). */
export function yearText(year: number): string {
  if (year < 0) return `${-year} BC`;
  return year < 1000 ? `AD ${year}` : `${year}`;
}

/** Why a place is known to have been worked by its year; null when it has no year. Never by colour alone (ADR 0019). */
export function datingText(
  place: Pick<
    PlaceProperties,
    | "worked_by_year"
    | "worked_by_basis"
    | "worked_by_note"
    | "worked_by_references"
    | "worked_by_period_end"
    | "upstream_worked_by_year"
    | "upstream_worked_by_note"
  >,
): string | null {
  if (place.worked_by_basis === "first production") return "From its first production, as MRDS records it";
  if (place.worked_by_basis === "period") return periodDatingText(place);
  if (place.worked_by_basis !== "curated") return null;
  const cited = workingDateReferences(place.worked_by_references).map((reference) => reference.citation);
  // A reason is written as a sentence; its full stop goes after the citations instead.
  const reason = (place.worked_by_note ?? "").replace(/\.$/, "");
  return `Curated date: ${reason}${cited.length ? ` (${cited.join("; ")})` : ""}.${upstreamText(place)}`;
}

/** A period that hadn't ended when the data was taken (Modern, to 2100) dates a place by that year, not by its end. */
function periodDatingText(place: Pick<PlaceProperties, "worked_by_year" | "worked_by_note" | "worked_by_period_end">): string {
  const period = place.worked_by_note ?? "a period";
  const running = place.worked_by_period_end != null && place.worked_by_year != null && place.worked_by_period_end > place.worked_by_year;
  return running ? `Attested in ${period}, which hadn't ended when the data was taken` : `Attested in ${period}, which had ended by then`;
}

/** What the dataset said, when a curated date replaces it, with the period its year came from. */
function upstreamText(place: Pick<PlaceProperties, "upstream_worked_by_year" | "upstream_worked_by_note">): string {
  if (place.upstream_worked_by_year == null) return "";
  const from = place.upstream_worked_by_note ? `, from ${place.upstream_worked_by_note}` : "";
  return ` The dataset says ${yearText(place.upstream_worked_by_year)}${from}.`;
}

/** The years a Pleiades place is attested, beside its year; null without either, since the state then gives the range. */
export function attestedText(
  place: Pick<PlaceProperties, "worked_by_year"> & Partial<Pick<PlaceProperties, "attested_from" | "attested_to">>,
): string | null {
  if (place.worked_by_year == null || place.attested_from == null || place.attested_to == null) return null;
  return `Attested ${attestedRange(place.attested_from, place.attested_to)}`;
}

function attestedRange(from: number, to: number): string {
  return `${yearText(from)} – ${untilText(to, new Date().getFullYear())}`;
}

function workingDateReferences(references: PlaceProperties["worked_by_references"]): WorkingDateReference[] {
  if (typeof references !== "string") return references ?? [];
  try {
    const parsed: unknown = JSON.parse(references);
    return Array.isArray(parsed) ? (parsed as WorkingDateReference[]) : [];
  } catch {
    return [];
  }
}

/** The end of an attested range: "the present" for Pleiades' modern periods, which end in years still to come (2100). */
export function untilText(year: number, thisYear: number): string {
  return year > thisYear ? "the present" : yearText(year);
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

/** A place against a profile's area and a year (ADR 0052): worked there by then, there but not known to be worked by
 * then, or outside the area. Without an area, a place is worked or present as its state says. */
export type Then = "worked" | "present" | "outside";

export function thenState(place: Pick<PlaceProperties, "state" | "worked_by_year" | "in_area">, year: number | null): Then {
  if (year === null) return place.state === "worked" ? "worked" : "present";
  if (place.in_area === false) return "outside";
  return place.worked_by_year != null && place.worked_by_year <= year ? "worked" : "present";
}

/** The features with each one's `then`, which the map's layers draw by. */
export function withThen(features: OccurrencesResponse["features"], year: number | null): OccurrencesResponse["features"] {
  return {
    ...features,
    features: features.features.map((feature) => ({
      ...feature,
      properties: { ...feature.properties, then: thenState(feature.properties, year) },
    })),
  };
}

/** What the popup says about a place and the profile's area: never by colour or shape alone (ADR 0019). */
export function areaText(place: Pick<PlaceProperties, "state" | "worked_by_year" | "in_area">, label: string, year: number): string {
  const then = thenState(place, year);
  if (then === "outside") return `Outside the area of ${label}`;
  if (then === "worked") return `Inside the area of ${label}, and worked by ${yearText(year)}`;
  return `Inside the area of ${label}, not known to be worked by ${yearText(year)}`;
}

/** The corners of an area, [[west, south], [east, north]], to fit the map to; null for an empty one. */
export function areaBounds(area: AreaGeometry): [[number, number], [number, number]] | null {
  const points = areaPoints(area);
  if (points.length === 0) return null;
  const xs = points.map((point) => point[0] ?? 0);
  const ys = points.map((point) => point[1] ?? 0);
  return [
    [Math.min(...xs), Math.min(...ys)],
    [Math.max(...xs), Math.max(...ys)],
  ];
}

function areaPoints(area: AreaGeometry): number[][] {
  if (area.type === "Polygon") return area.coordinates.flat();
  if (area.type === "MultiPolygon") return area.coordinates.flat(2);
  return area.geometries.flatMap(areaPoints);
}
