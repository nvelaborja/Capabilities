import type { ProfileMap, ProfileSource } from "../api/types";
import { yearText } from "../map/places";

/** Where and when a profile is, and whose borders say so: "Middle Kingdom of Egypt, 2050 BC to 1650 BC". */
export function placeLine(place: ProfileMap): string {
  const [first, last] = place.years;
  return `${place.cliopatria}, ${yearText(first)} to ${yearText(last)}`;
}

/** Which borders the area is, and when Cliopatria's rows for it start and end, when that differs from the profile. */
export function bordersLine(place: ProfileMap): string {
  const release = place.release ? ` ${place.release}` : "";
  const [first, last] = place.cliopatria_years;
  const rows = place.cliopatria_rows === 1 ? "1 map" : `${place.cliopatria_rows} maps`;
  return `Borders from Cliopatria${release}: ${rows}, ${yearText(first)} to ${yearText(last)}.`;
}

/** What a source found in the area says, inside its chip: never by colour or border alone (ADR 0019). */
export function sourceNote(source: ProfileSource, last: number): string {
  if (source.availability === "yes") return `had: ${count(source.worked_by_then, "place")} worked by ${yearText(last)}`;
  return `maybe: ${count(source.not_known_worked, "place")}, none known worked by then`;
}

/** The longer reading, for the chip's tooltip; the detail pane and the map say the same. */
export function sourceTitle(source: ProfileSource): string {
  if (source.kind === "category") {
    return "An ore class: the mines here don't say which ore, so it isn't added. Add the ore's source if you know it.";
  }
  if (source.from_map) return "Added to the selection by the map. Remove it to leave it out.";
  if (source.listed) return "Also in the preset's own list.";
  if (source.availability === "maybe") return "Present, not known to be worked by then: add it if you believe it was.";
  return "";
}

/** How many source kinds the map found, in the folded summary: "1 had, 6 maybe". */
export function countsLine(place: ProfileMap): string {
  const { had, maybe } = sourcesByAvailability(place);
  if (had.length + maybe.length === 0) return "nothing found in the area";
  return `${had.length} had, ${maybe.length} maybe`;
}

/** Had sources first, then the maybes, each by name, as the API sends them. */
export function sourcesByAvailability(place: ProfileMap): { had: ProfileSource[]; maybe: ProfileSource[] } {
  return {
    had: place.sources.filter((source) => source.availability === "yes"),
    maybe: place.sources.filter((source) => source.availability === "maybe"),
  };
}

const count = (n: number, noun: string) => `${n.toLocaleString("en")} ${noun}${n === 1 ? "" : "s"}`;
