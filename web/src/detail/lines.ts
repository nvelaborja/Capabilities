import type { RequirementRole } from "../api/types";

export interface LineStyle {
  /** How the line looks on the graph. */
  look: string;
  /** What that look means. */
  meaning: string;
}

const ROLE_LINES: Record<RequirementRole, LineStyle> = {
  consumed: { look: "Solid line", meaning: "an ingredient, used up in the making" },
  tool: { look: "Dashed line", meaning: "a tool, used but not used up" },
  action: { look: "Dotted line", meaning: "an action that has to be done along the way" },
  effect: { look: "Solid line with a label", meaning: "a condition to reach, such as heat; the label is the threshold" },
};

/**
 * Why a line on the graph looks the way it does (graph/styles.ts draws it). Lines merge every route that links the
 * same two nodes, so one line can stand for several roles; then it is drawn solid.
 */
export function lineStyle(kind: "requires" | "is_a", roles: readonly RequirementRole[], byproduct: boolean): LineStyle {
  if (kind === "is_a") return { look: "Thin dashed line, no arrow", meaning: "is a kind of: any route that needs the kind can use it" };
  if (byproduct) return { look: "Dotted line", meaning: "made as a byproduct, not the route's goal" };
  const distinct = [...new Set(roles)];
  const only = distinct.length === 1 ? distinct[0] : undefined;
  if (only) return ROLE_LINES[only];
  return { look: "Solid line", meaning: `used in more than one way (${distinct.map((role) => ROLE_LINES[role].meaning.split(",")[0]).join("; ")})` };
}
