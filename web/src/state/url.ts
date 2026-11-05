import type { Selection } from "./selection";

/**
 * Shareable links hold the preset plus changes (ADR 0017): ?preset=middle-kingdom-egypt&add=hematite,cut:wood&remove=sledge.
 * Short, readable, and the same shape as the explore request.
 */
export function encodeSelection(selection: Selection): string {
  const params = new URLSearchParams();
  if (selection.preset) params.set("preset", selection.preset);
  if (selection.added.length > 0) params.set("add", selection.added.join(","));
  if (selection.removed.length > 0) params.set("remove", selection.removed.join(","));
  const query = params.toString().replaceAll("%2C", ",").replaceAll("%3A", ":");
  return query ? `?${query}` : "";
}

export function decodeSelection(search: string): Selection {
  const params = new URLSearchParams(search);
  const list = (key: string) =>
    [...new Set((params.get(key) ?? "").split(",").map((item) => item.trim()).filter(Boolean))].sort();
  return { preset: params.get("preset") || null, added: list("add"), removed: list("remove") };
}
