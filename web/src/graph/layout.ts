import cytoscape, { type Core, type EdgeSingular, type NodeCollection } from "cytoscape";
import dagre from "cytoscape-dagre";

cytoscape.use(dagre);

/** Below this zoom, node labels are too small to read, so the first view zooms in to it instead of fitting all. */
export const READABLE_ZOOM = 0.8;
/** Horizontal distance between layout columns. Things are two columns apart, with route dots in between. */
export const COLUMN_GAP = 110;
const ROW_GAP = 14;
const PADDING = 24;
const LABEL_OFFSET = 56;

/**
 * The shortest an edge may be, in layout columns. Asking dagre for at least the tech-level gap gives it a vertical
 * order that suits the columns the nodes are then snapped to. Backward edges (cycles) fall back to the minimum.
 */
export function minimumLength(sourceRank: number | null, targetRank: number | null): number {
  if (sourceRank === null || targetRank === null) return 1;
  return Math.max(1, targetRank - sourceRank);
}

const DAGRE: dagre.DagreLayoutOptions = {
  name: "dagre",
  rankDir: "LR",
  nodeSep: 14,
  rankSep: 56,
  edgeSep: 6,
  padding: PADDING,
  animate: false,
  fit: false,
  minLen: (edge: EdgeSingular) =>
    minimumLength(edge.source().data("rank") as number | null, edge.target().data("rank") as number | null),
};

/**
 * Lay the graph out as a technology tree (ADR 0018): one column per tech level, primitives on the left. Dagre gives
 * a first top-to-bottom order; a few barycentre sweeps then pull each node towards its neighbours in nearby columns,
 * and each column is stacked tightly around the middle.
 */
export function runLayout(cy: Core): void {
  cy.remove(".level-label");
  cy.elements().not("edge.is_a").layout(DAGRE).run();
  const ranks = resolveRanks(cy);
  const columns = new Map<number, string[]>();
  const byDagre = cy.nodes().sort((a, b) => a.position("y") - b.position("y"));
  byDagre.forEach((node) => {
    const rank = ranks.get(node.id()) ?? 0;
    columns.set(rank, [...(columns.get(rank) ?? []), node.id()]);
  });
  // "Is a" links are left out: they would pull categories towards their members.
  const links: [string, string][] = [];
  cy.edges().forEach((edge) => {
    if (!edge.hasClass("is_a")) links.push([edge.source().id(), edge.target().id()]);
  });
  const ordered = orderByBarycentre(columns, ranks, links);
  cy.batch(() => {
    for (const [rank, ids] of ordered) {
      const items = ids.map((id) => ({ id, height: cy.getElementById(id).data("height") as number }));
      for (const [id, y] of stackColumn(items, ROW_GAP)) {
        cy.getElementById(id).position({ x: rank * COLUMN_GAP, y });
      }
    }
  });
  addLevelLabels(cy, [...ordered.keys()]);
}

/**
 * Reorder each column so nodes sit near the average position of their neighbours: left to right using links from
 * earlier columns, then right to left using links to later ones. The classic way to reduce crossings in layered
 * drawings. Nodes without neighbours in that direction keep their place.
 */
export function orderByBarycentre(
  columns: Map<number, string[]>,
  ranks: Map<string, number>,
  links: [string, string][],
  sweeps = 3,
): Map<number, string[]> {
  const result = new Map([...columns].map(([rank, ids]) => [rank, [...ids]]));
  const position = new Map<string, number>();
  const placeColumn = (ids: string[]) => ids.forEach((id, index) => position.set(id, index - (ids.length - 1) / 2));
  result.forEach(placeColumn);
  const order = [...result.keys()].sort((a, b) => a - b);

  const reorder = (rank: number, neighbourOf: (id: string) => string[]) => {
    const ids = result.get(rank) ?? [];
    const key = (id: string) => {
      const ys = neighbourOf(id).map((n) => position.get(n)).filter((y): y is number => y !== undefined);
      return ys.length > 0 ? mean(ys) : (position.get(id) ?? 0);
    };
    const keys = new Map(ids.map((id) => [id, key(id)]));
    const sorted = [...ids].sort((a, b) => (keys.get(a) ?? 0) - (keys.get(b) ?? 0));
    result.set(rank, sorted);
    placeColumn(sorted);
  };

  const rankOf = (id: string) => ranks.get(id) ?? 0;
  const fromLeft = (id: string) => links.filter(([, t]) => t === id).map(([s]) => s).filter((s) => rankOf(s) < rankOf(id));
  const toRight = (id: string) => links.filter(([s]) => s === id).map(([, t]) => t).filter((t) => rankOf(t) > rankOf(id));
  for (let sweep = 0; sweep < sweeps; sweep++) {
    order.forEach((rank) => reorder(rank, fromLeft));
    [...order].reverse().forEach((rank) => reorder(rank, toRight));
  }
  return result;
}

/** Stack a column's nodes in order, a fixed gap apart, centred on y = 0. */
export function stackColumn(items: { id: string; height: number }[], gap: number): Map<string, number> {
  const total = items.reduce((sum, item) => sum + item.height, 0) + gap * Math.max(0, items.length - 1);
  const placed = new Map<string, number>();
  let top = -total / 2;
  for (const item of items) {
    placed.set(item.id, top + item.height / 2);
    top += item.height + gap;
  }
  return placed;
}

/**
 * Each node's column. Things and actions come from their tech level; nodes without one (verb routes, things with
 * no known route) go one column right of what feeds them, else one column left of what they feed.
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
  // Unranked nodes can depend on each other (a verb route fed only by an unranked thing), hence a few passes.
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

function mean(values: number[]): number {
  return values.length === 0 ? 0 : values.reduce((sum, value) => sum + value, 0) / values.length;
}

/** A "Level N" heading just above each column of things (even ranks), so the tree reads left to right. */
function addLevelLabels(cy: Core, ranks: number[]): void {
  const levels = ranks.filter((rank) => rank % 2 === 0).sort((a, b) => a - b);
  cy.add(
    levels.map((rank) => {
      const column = cy.nodes().filter((node) => node.position("x") === rank * COLUMN_GAP);
      return {
        group: "nodes" as const,
        data: { id: `level-label-${rank / 2}`, label: `Level ${rank / 2}`, width: 80, height: 24 },
        position: { x: rank * COLUMN_GAP, y: column.boundingBox().y1 - LABEL_OFFSET / 2 },
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
