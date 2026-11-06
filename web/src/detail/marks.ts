import type { RouteRow, Status, Tri } from "../api/types";

/** ✓ met, ✗ missing, ? unknown. The glyph and its words carry the meaning; colour only reinforces it. */
export const MARKS: Record<Tri, { glyph: string; label: string }> = {
  yes: { glyph: "✓", label: "met" },
  no: { glyph: "✗", label: "missing" },
  maybe: { glyph: "?", label: "unknown" },
};

/** Whether the selection has (or could make) an item, as a three-valued answer. */
export function statusTri(status: Status | undefined): Tri {
  switch (status) {
    case "selected":
    case "hypothetical":
    case "implied":
    case "reachable":
      return "yes";
    case "maybe":
      return "maybe";
    default:
      return "no";
  }
}

/**
 * The status border for an item shown in the detail pane: where the selection puts it, or, for items the explore
 * result doesn't cover, a status from the three-valued answer.
 */
export function chipStatus(status: Status | undefined, tri: Tri): Status {
  if (status) return status;
  return tri === "yes" ? "reachable" : tri === "maybe" ? "maybe" : "out";
}

/** "Works", "Missing 1", "Missing 2 · 1 unknown", "1 unknown". */
export function routeVerdict(route: Pick<RouteRow, "status" | "missing" | "uncertain">): string {
  if (route.status === "yes") return "Works";
  const parts = [];
  if (route.missing > 0) parts.push(`Missing ${route.missing}`);
  if (route.uncertain > 0) parts.push(`${route.uncertain} unknown`);
  return parts.join(" · ") || (route.status === "maybe" ? "Might work" : "Doesn't work");
}

export const KIND_NAMES: Record<string, { one: string; many: string }> = {
  material: { one: "Material", many: "Materials" },
  artifact: { one: "Tool or product", many: "Tools and products" },
  action: { one: "Action", many: "Actions" },
  category: { one: "Any of a kind", many: "Any of a kind" },
  effect: { one: "Effect", many: "Conditions" },
  technique: { one: "Know-how", many: "Know-how" },
};

export function kindName(kind: string, count = 1): string {
  const names = KIND_NAMES[kind];
  if (!names) return kind;
  return count === 1 ? names.one : names.many;
}

/** The heading over a node's routes: things are made, effects reached, actions done. */
export function waysHeading(kind: string): string {
  if (kind === "action") return "Ways to do it";
  if (kind === "effect") return "Ways to reach it";
  return "Ways to make it";
}

/** Requirement roles worth naming; effects and actions explain themselves. */
export const ROLE_TAGS: Partial<Record<string, string>> = { consumed: "used up", tool: "tool" };
