import type { ExploreResponse, Status } from "../api/types";
import type { Catalog, ItemKind } from "../catalog";
import { noun } from "../lib/bounded";

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

/** Many chips folded under one, such as every target of a verb ("Cut · 19 materials"), opened on demand. */
export interface ChipGroup {
  key: string;
  label: string;
  kind: ItemKind;
  status: Status;
  /** How many there are, by type: "19 materials", "4 materials (2 maybe)". */
  note: string;
  chips: Chip[];
}

/** A titled part of a list. Chips are sorted by type, then name; the type shows on each chip, so there are no type headings. */
export interface Section {
  key: string;
  title: string;
  hint?: string;
  /** Folded chips, each on its own line before the plain chips. */
  groups?: ChipGroup[];
  chips: Chip[];
}

const KIND_ORDER: ItemKind[] = ["source", "material", "artifact", "action", "category", "effect", "technique"];

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
  const { groups: verbs, single } = groupByVerb(actions, catalog);
  const near = explore.near.map((item) =>
    chip(item.id, "near", { note: `add ${[...new Set(item.routes.map((route) => route.missing.label.toLowerCase()))].join(" or ")}` }),
  );

  const sections: Section[] = [
    { key: "implied", title: "Implied", hint: "Required by the selection", chips: implied.sort(byTypeThenLabel) },
    { key: "reachable", title: "Could make", chips: things.sort(byTypeThenLabel) },
    { key: "actions", title: "Could do", groups: verbs, chips: single.sort(byTypeThenLabel) },
    { key: "near", title: "One step away", hint: "One more raw ingredient would unlock these", chips: near.sort(byTypeThenLabel) },
  ];
  return sections.filter((section) => sectionCount(section) > 0);
}

/**
 * Fold the actions of each verb with several targets into one chip that says how many there are ("Cut · 19 materials",
 * opened to see them all). A verb with one target stays a plain chip.
 */
export function groupByVerb(actions: readonly Chip[], catalog: Catalog): { groups: ChipGroup[]; single: Chip[] } {
  const byVerb = new Map<string, Chip[]>();
  for (const action of actions) {
    const verb = action.id.split(":", 1)[0] ?? action.id;
    byVerb.set(verb, [...(byVerb.get(verb) ?? []), action]);
  }
  const groups: ChipGroup[] = [];
  const single: Chip[] = [];
  for (const [verb, chips] of byVerb) {
    if (chips.length === 1) {
      single.push(...chips);
      continue;
    }
    const maybes = chips.filter((c) => c.status === "maybe").length;
    groups.push({
      key: verb,
      label: catalog.verb(verb),
      kind: "action",
      status: maybes === chips.length ? "maybe" : "reachable",
      note: `${chips.length} ${targetNoun(chips, catalog)}${maybes > 0 && maybes < chips.length ? ` (${maybes} maybe)` : ""}`,
      chips: chips.sort(byTypeThenLabel),
    });
  }
  groups.sort((a, b) => a.label.localeCompare(b.label));
  return { groups, single };
}

/** "materials" when every target is a material, else "things". */
function targetNoun(actions: readonly Chip[], catalog: Catalog): string {
  const kinds = new Set(actions.map((action) => catalog.get(action.id.split(":", 2)[1] ?? "").kind));
  const [only] = kinds;
  return kinds.size === 1 && only ? noun(only, actions.length) : "things";
}

/** Every item in a section, folded or not. */
export function sectionCount(section: Section): number {
  return section.chips.length + (section.groups ?? []).reduce((total, group) => total + group.chips.length, 0);
}

export function countChips(sections: readonly Section[]): number {
  return sections.reduce((total, section) => total + sectionCount(section), 0);
}
