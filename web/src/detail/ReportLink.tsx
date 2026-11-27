import { type ReportedFact, reportUrl } from "./report";

/** Opens the report form on GitHub in a new tab, about one fact (ADR 0050). */
export function ReportLink({ text = "Report a problem", ...fact }: ReportedFact & { text?: string }) {
  return (
    <a className="report-link" href={reportUrl(fact)} target="_blank" rel="noreferrer">
      {text}
    </a>
  );
}
