/**
 * "Report a problem" (ADR 0050): a link to a new GitHub issue on the report form (.github/ISSUE_TEMPLATE/report.yml),
 * with the fact filled in. Nothing is sent or stored by the app; the reader writes the issue on GitHub, and open
 * reports join the curation queue at the next build.
 */
export const REPOSITORY = "https://github.com/nvelaborja/Capabilities";

export interface ReportedFact {
  /** The node or route id, or "a → b" for a line. */
  fact: string;
  kind: "node" | "route" | "reference" | "line";
  /** How the app names it, for the issue's title. */
  label: string;
  /** A reference's citation. */
  reference?: string;
  /** The agent run that proposed it, if one did. */
  run?: string;
}

export function reportUrl({ fact, kind, label, reference, run }: ReportedFact): string {
  // The form's fields are filled in from query parameters named by their ids.
  const params = new URLSearchParams({ template: "report.yml", title: `Report: ${label}`, fact, kind });
  if (reference) params.set("reference", reference);
  if (run) params.set("run", run);
  return `${REPOSITORY}/issues/new?${params.toString()}`;
}
