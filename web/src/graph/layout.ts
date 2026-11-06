import type { Core, NodeCollection } from "cytoscape";

import { OUTSIDE } from "./focus";
import { TYPED_KINDS } from "./styles";

/** Below this zoom, node labels are too small to read, so the first view zooms in to it instead of fitting all. */
export const READABLE_ZOOM = 0.8;
/** Horizontal distance between tech-level columns. */
export const COLUMN_GAP = 230;
const ROW_GAP = 14;
/** Extra space between type groups within a column (materials, then tools, then actions...). */
const GROUP_GAP = 18;
const PADDING = 24;
const LABEL_OFFSET = 28;

export interface ColumnItem {
  id: string;
  label: string;
  kind: string;
  height: number;
}

/**
 * Lay the graph out as a technology tree (ADR 0018, 0023): one column per tech level, primitives on the left.
 * Within a column, nodes are sorted by type, then alphabetically, like the lists in the side pane; summary nodes go
 * last. Only nodes that are showing are placed, so focus mode closes up the gaps.
 */
export function runLayout(cy: Core): void {
  cy.remove(".level-label");
  const ranks = resolveRanks(cy);
  const columns = new Map<number, ColumnItem[]>();
  cy.nodes().not(`.${OUTSIDE}`).forEach((node) => {
    const rank = ranks.get(node.id()) ?? 0;
    const item = { id: node.id(), label: node.data("label") as string, kind: node.data("kind") as string, height: node.data("height") as number };
    columns.set(rank, [...(columns.get(rank) ?? []), item]);
  });
  cy.batch(() => {
    for (const [rank, items] of columns) {
      for (const [id, y] of stackColumn(sortColumn(items))) {
        cy.getElementById(id).position({ x: rank * COLUMN_GAP, y });
      }
    }
  });
  addLevelLabels(cy, [...columns.keys()]);
}

const typeIndex = (kind: string) => {
  const index = (TYPED_KINDS as readonly string[]).indexOf(kind);
  return index === -1 ? TYPED_KINDS.length : index;
};

/** Type first (materials, tools and products, actions, categories, effects), then alphabetically by label. */
export function sortColumn(items: ColumnItem[]): ColumnItem[] {
  return [...items].sort(
    (a, b) => typeIndex(a.kind) - typeIndex(b.kind) || a.label.localeCompare(b.label, undefined, { sensitivity: "base" }),
  );
}

/** Stack a column's nodes in order, centred on y = 0, with a little more space where the type changes. */
export function stackColumn(items: ColumnItem[]): Map<string, number> {
  const gaps = items.map((item, index) => {
    const previous = items[index - 1];
    if (!previous) return 0;
    return previous.kind === item.kind ? ROW_GAP : ROW_GAP + GROUP_GAP;
  });
  const total = items.reduce((sum, item, index) => sum + item.height + (gaps[index] ?? 0), 0);
  const placed = new Map<string, number>();
  let top = -total / 2;
  items.forEach((item, index) => {
    top += gaps[index] ?? 0;
    placed.set(item.id, top + item.height / 2);
    top += item.height;
  });
  return placed;
}

/**
 * Each node's column. Things and actions come from their tech level; nodes without one (things with no known
 * route, such as the modern diamond saw) go one column right of what feeds them, else one column left of what they
 * feed.
 */
export function resolveRanks(cy: Core): Map<string, number> {
  const ranks = new Map<string, number>();
  const nodes = cy.nodes().not(".level-label");
  nodes.forEach((node) => {
    const rank = node.data("rank") as number | null;
    if (typeof rank === "number") ranks.set(node.id(), rank);
  });
  const known = (collection: NodeCollection) =>
    collection.map((n) => ranks.get(n.id())).filter((rank): rank is number => rank !== undefined);
  // Unranked nodes can depend on each other, hence a few passes.
  for (let pass = 0; pass < 3; pass++) {
    nodes.forEach((node) => {
      if (ranks.has(node.id())) return;
      const fedBy = known(node.incomers("node"));
      const feeds = known(node.outgoers("node"));
      if (fedBy.length > 0) ranks.set(node.id(), Math.max(...fedBy) + 1);
      else if (feeds.length > 0) ranks.set(node.id(), Math.max(0, Math.min(...feeds) - 1));
    });
  }
  nodes.forEach((node) => {
    if (!ranks.has(node.id())) ranks.set(node.id(), 0);
  });
  return ranks;
}

/** A "Level N" heading just above each column, so the tree reads left to right. */
function addLevelLabels(cy: Core, ranks: number[]): void {
  const levels = [...ranks].sort((a, b) => a - b);
  cy.add(
    levels.map((rank) => {
      const column = cy.nodes().filter((node) => !node.hasClass(OUTSIDE) && node.position("x") === rank * COLUMN_GAP);
      return {
        group: "nodes" as const,
        data: { id: `level-label-${rank}`, label: `Level ${rank}`, width: 80, height: 24 },
        position: { x: rank * COLUMN_GAP, y: column.boundingBox().y1 - LABEL_OFFSET },
        classes: ["level-label"],
        selectable: false,
        grabbable: false,
      };
    }),
  );
}

/** Fit the graph if its labels stay readable; otherwise zoom to a readable size around what matters most. */
export function showInitialView(cy: Core, focus?: NodeCollection): void {
  cy.fit(undefined, PADDING);
  if (cy.zoom() >= READABLE_ZOOM) return;
  const target = focus && focus.nonempty() ? focus : cy.nodes();
  cy.zoom(READABLE_ZOOM);
  cy.center(target);
}
