import type { Core } from "cytoscape";

import { LIMIT } from "../lib/bounded";
import { FOLDED, OUTSIDE } from "./focus";
import { foldedEdges, type HubNode, summarise, type Summary } from "./summaries";

const SUMMARY_HEIGHT = 26;
const CHAR_WIDTH = 6.5;

/**
 * Replace the graph's summary nodes: fold each hub's extra edges into "8 other materials" nodes (ADR 0024). Only
 * what is showing counts, so focus mode summarises its own subgraph. Returns the summaries now drawn.
 */
export function applySummaries(cy: Core, expanded: ReadonlySet<string>, limit = LIMIT): Summary[] {
  cy.remove(".summary");
  cy.edges().removeClass(FOLDED);
  const showing = cy.nodes().not(`.level-label, .${OUTSIDE}`);
  const nodes: HubNode[] = showing.map((node) => ({
    id: node.id(),
    label: node.data("label") as string,
    kind: node.data("kind") as string,
    level: (node.data("level") as number | null) ?? null,
    prerequisites: (node.data("prerequisites") as number | undefined) ?? 0,
  }));
  const edges = cy
    .edges()
    .filter((edge) => !edge.hasClass(OUTSIDE))
    .map((edge) => ({ id: edge.id(), source: edge.data("source") as string, target: edge.data("target") as string }));
  const summaries = summarise(nodes, edges, limit).filter((summary) => !expanded.has(summary.id));
  cy.batch(() => {
    cy.add(
      summaries.flatMap((summary) => [
        {
          group: "nodes" as const,
          data: {
            id: summary.id, label: summary.label, kind: "summary", rank: null, members: summary.members,
            width: Math.round(summary.label.length * CHAR_WIDTH + 24), height: SUMMARY_HEIGHT,
          },
          classes: ["summary"],
        },
        {
          group: "edges" as const,
          data: {
            id: `${summary.id}/edge`,
            label: "",
            source: summary.direction === "out" ? summary.hub : summary.id,
            target: summary.direction === "out" ? summary.id : summary.hub,
          },
          classes: ["summary-edge"],
        },
      ]),
    );
    refold(cy, summaries, expanded);
  });
  return summaries;
}

/** Expand one summary in place: its edges come back and nothing else moves. */
export function expandSummary(cy: Core, summaries: readonly Summary[], expanded: Set<string>, id: string): void {
  expanded.add(id);
  cy.batch(() => {
    cy.getElementById(id).remove();
    refold(cy, summaries, expanded);
  });
}

function refold(cy: Core, summaries: readonly Summary[], expanded: ReadonlySet<string>): void {
  const folded = foldedEdges(summaries, expanded);
  cy.edges().forEach((edge) => {
    edge.toggleClass(FOLDED, folded.has(edge.id()));
  });
}
