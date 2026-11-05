import type { ExploreResponse } from "../api/types";
import type { Catalog, ItemKind } from "../catalog";

export interface Row {
  id: string;
  label: string;
  /** Explicit selections can be removed; implied ones can't (remove what implies them instead, ADR 0017). */
  removable: boolean;
  badge?: "implied" | "maybe";
  note?: string;
}

export interface Group {
  key: string;
  title: string;
  rows: Row[];
}

// Lists are sorted by type, then alphabetically (design doc, item 4).
const GROUP_ORDER: { kind: ItemKind; title: string }[] = [
  { kind: "material", title: "Materials" },
  { kind: "artifact", title: "Tools and products" },
  { kind: "action", title: "Actions" },
  { kind: "category", title: "Any of a kind" },
  { kind: "effect", title: "Conditions reached" },
  { kind: "technique", title: "Know-how" },
];

const byLabel = (a: Row, b: Row) => a.label.localeCompare(b.label, undefined, { sensitivity: "base" });

function grouped(rows: { kind: ItemKind; row: Row }[]): Group[] {
  return GROUP_ORDER.map(({ kind, title }) => ({
    key: kind,
    title,
    rows: rows.filter((entry) => entry.kind === kind).map((entry) => entry.row).sort(byLabel),
  })).filter((group) => group.rows.length > 0);
}

function neededBy(explore: ExploreResponse, catalog: Catalog, id: string): string | undefined {
  const sources = explore.implied_by[id];
  if (!sources || sources.length === 0) return undefined;
  const names = sources.map((source) => catalog.get(source).label.toLowerCase());
  const shown = names.slice(0, 3).join(", ");
  return `Needed by ${shown}${names.length > 3 ? ` and ${names.length - 3} more` : ""}`;
}

/** The Selected list: explicit selections, then everything they certainly needed (implied). */
export function selectedGroups(explore: ExploreResponse, catalog: Catalog): Group[] {
  const explicit = new Set([...explore.selected, ...explore.hypothetical]);
  const rows: { kind: ItemKind; row: Row }[] = [];
  for (const id of explicit) {
    const { label, kind } = catalog.get(id);
    rows.push({ kind, row: { id, label, removable: true } });
  }
  const implied = [
    ...explore.implied.things,
    ...explore.implied.actions,
    ...explore.implied.categories,
    ...explore.implied.techniques,
  ];
  for (const id of implied) {
    if (explicit.has(id)) continue;
    const { label, kind } = catalog.get(id);
    rows.push({ kind, row: { id, label, removable: false, badge: "implied", note: neededBy(explore, catalog, id) } });
  }
  for (const effect of explore.implied_effects) {
    const label = `${effect.label} (${effect.conditions.join(", ").toLowerCase()})`;
    rows.push({ kind: "effect", row: { id: effect.id, label, removable: false, badge: "implied", note: neededBy(explore, catalog, effect.id) } });
  }
  return grouped(rows);
}

/** The Reachable list: what could be made or done from the selection, beyond what is already in it. */
export function reachableGroups(explore: ExploreResponse, catalog: Catalog): Group[] {
  const have = new Set([...explore.selected, ...explore.hypothetical, ...explore.implied.things, ...explore.implied.actions]);
  const rows: { kind: ItemKind; row: Row }[] = [];
  for (const id of explore.reachable) {
    const { label, kind } = catalog.get(id);
    rows.push({ kind, row: { id, label, removable: false } });
  }
  for (const id of explore.maybe) {
    const { label, kind } = catalog.get(id);
    rows.push({ kind, row: { id, label, removable: false, badge: "maybe" } });
  }
  const groups = grouped(rows);
  // Actions come grouped by verb ("Cut: 19"), since every verb applies to many targets.
  for (const [verb, targets] of Object.entries(explore.actions).sort(([a], [b]) => a.localeCompare(b))) {
    const actionRows = Object.entries(targets)
      .map(([target, status]) => ({ id: `${verb}:${target}`, status }))
      .filter(({ id }) => !have.has(id))
      .map(({ id, status }): Row => ({ id, label: catalog.get(id).label, removable: false, badge: status === "maybe" ? "maybe" : undefined }))
      .sort(byLabel);
    if (actionRows.length > 0) {
      groups.push({ key: `verb-${verb}`, title: catalog.verb(verb), rows: actionRows });
    }
  }
  return groups;
}

export function countRows(groups: Group[]): number {
  return groups.reduce((total, group) => total + group.rows.length, 0);
}
