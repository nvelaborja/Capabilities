/**
 * Show a bounded number of items (ADR 0020): when a list has more than LIMIT items, the first LIMIT are shown and the
 * rest are summarised by type ("43 other materials"). Callers pass items already ranked (ADR 0018), so what is shown
 * depends only on how many items there are, never on what kind they are.
 */
export const LIMIT = 8;

export interface Hidden<T> {
  kind: string;
  items: T[];
}

export interface Bounded<T> {
  shown: T[];
  /** One group per kind, in the order the kinds first appear among the hidden items. */
  hidden: Hidden<T>[];
}

export function bound<T>(items: readonly T[], kindOf: (item: T) => string, limit = LIMIT): Bounded<T> {
  if (items.length <= limit) return { shown: [...items], hidden: [] };
  const groups = new Map<string, T[]>();
  for (const item of items.slice(limit)) {
    const kind = kindOf(item);
    groups.set(kind, [...(groups.get(kind) ?? []), item]);
  }
  return { shown: items.slice(0, limit), hidden: [...groups].map(([kind, grouped]) => ({ kind, items: grouped })) };
}

const NOUNS: Record<string, [string, string]> = {
  material: ["material", "materials"],
  artifact: ["tool or product", "tools and products"],
  action: ["action", "actions"],
  category: ["class", "classes"],
  effect: ["effect", "effects"],
  technique: ["technique", "techniques"],
  route: ["way", "ways"],
};

/** "43 other materials", "1 other tool or product". */
export function summaryLabel(kind: string, count: number): string {
  return `${count} other ${noun(kind, count)}`;
}

/** "materials", "tool or product". */
export function noun(kind: string, count: number): string {
  const [one, many] = NOUNS[kind] ?? ["item", "items"];
  return count === 1 ? one : many;
}
