import type { ExploreResponse, Status } from "../api/types";
import type { Catalog, ItemKind } from "../catalog";

/** One item in the side pane, drawn like a graph node: type strip with emoji, status border (ADR 0025). */
export interface Chip {
  id: string;
  label: string;
  kind: ItemKind;
  status: Status;
  /** Explicit selections can be removed; implied ones can't (remove what implies them instead, ADR 0017). */
  removable: boolean;
  /** Short visible text inside the chip, such as what a near miss is missing. */
  note?: string;
  /** Extra detail for the tooltip; the same information is always in the detail pane (ADR 0019). */
  title?: string;
}

/** A titled part of a list. Chips are sorted by type, then name; the type shows on each chip, so there are no type headings. */
export interface Section {
  key: string;
  title: string;
  hint?: string;
  chips: Chip[];
}

const KIND_ORDER: ItemKind[] = ["material", "artifact", "action", "category", "effect", "technique"];

const byTypeThenLabel = (a: Chip, b: Chip) =>
  KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind) || a.label.localeCompare(b.label, undefined, { sensitivity: "base" });

/** Consecutive chips of the same kind, so each type starts on its own line. */
export function byKind(chips: readonly Chip[]): Chip[][] {
  const runs: Chip[][] = [];
  for (const chip of chips) {
    const last = runs.at(-1);
    if (last && last[0]?.kind === chip.kind) last.push(chip);
    else runs.push([chip]);
  }
  return runs;
}

function neededBy(explore: ExploreResponse, catalog: Catalog, id: string): string | undefined {
  const sources = explore.implied_by[id];
  if (!sources || sources.length === 0) return undefined;
  return `Needed by ${sources.map((source) => catalog.get(source).label.toLowerCase()).join(", ")}`;
}

/** The top list: only what the user chose (explicit and what-if), sorted by type, then name. */
export function selectedChips(explore: ExploreResponse, catalog: Catalog): Chip[] {
  const hypothetical = new Set(explore.hypothetical);
  return [...explore.selected, ...explore.hypothetical]
    .map((id): Chip => {
      const { label, kind } = catalog.get(id);
      return { id, label, kind, status: hypothetical.has(id) ? "hypothetical" : "selected", removable: true };
    })
    .sort(byTypeThenLabel);
}

/**
 * The bottom list: what the selection requires, what could be made or done from it, and what one more raw ingredient
 * would unlock. Nothing already chosen appears here.
 */
export function withinReach(explore: ExploreResponse, catalog: Catalog): Section[] {
  const chosen = new Set([...explore.selected, ...explore.hypothetical]);
  const chip = (id: string, status: Status, extra: Partial<Chip> = {}): Chip => {
    const { label, kind } = catalog.get(id);
    return { id, label, kind, status, removable: false, ...extra };
  };

  const implied = [...explore.implied.things, ...explore.implied.actions, ...explore.implied.categories, ...explore.implied.techniques]
    .filter((id) => !chosen.has(id))
    .map((id) => chip(id, "implied", { title: neededBy(explore, catalog, id) }));
  for (const effect of explore.implied_effects) {
    implied.push({
      id: effect.id, label: effect.label, kind: "effect", status: "implied", removable: false,
      note: effect.conditions.join(", "), title: neededBy(explore, catalog, effect.id),
    });
  }

  const have = new Set([...chosen, ...implied.map((c) => c.id)]);
  const things = [
    ...explore.reachable.map((id) => chip(id, "reachable")),
    ...explore.maybe.map((id) => chip(id, "maybe", { note: "maybe" })),
  ].filter((c) => !have.has(c.id));
  // Actions sort by label, which starts with the verb, so they read "Cut granite, Cut limestone, Drill…".
  const actions = Object.entries(explore.actions)
    .flatMap(([verb, targets]) => Object.entries(targets).map(([target, tri]) => ({ id: `${verb}:${target}`, tri })))
    .filter(({ id }) => !have.has(id))
    .map(({ id, tri }) => chip(id, tri === "maybe" ? "maybe" : "reachable", tri === "maybe" ? { note: "maybe" } : {}));
  const near = explore.near.map((item) =>
    chip(item.id, "near", { note: `add ${[...new Set(item.routes.map((route) => route.missing.label.toLowerCase()))].join(" or ")}` }),
  );

  const sections: Section[] = [
    { key: "implied", title: "Implied", hint: "Required by the selection", chips: implied.sort(byTypeThenLabel) },
    { key: "reachable", title: "Could make", chips: things.sort(byTypeThenLabel) },
    { key: "actions", title: "Could do", chips: actions.sort(byTypeThenLabel) },
    { key: "near", title: "One step away", hint: "One more raw ingredient would unlock these", chips: near.sort(byTypeThenLabel) },
  ];
  return sections.filter((section) => section.chips.length > 0);
}

export function countChips(sections: readonly Section[]): number {
  return sections.reduce((total, section) => total + section.chips.length, 0);
}
