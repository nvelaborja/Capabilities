import type { Reference } from "../api/types";
import { checkSegments, linkStateText } from "./referenceCheck";
import { ReportLink } from "./ReportLink";

const STATUS_TEXT: Record<NonNullable<Reference["status"]>, string> = {
  verified: "verified",
  secondary: "from a summary",
  unverified: "not yet checked",
};

interface ReferencesProps {
  references: readonly Reference[];
  /** The node or route citing them: what a report about one names. */
  owner: { id: string; label: string };
}

/** Where a claim comes from, and how carefully it was checked (docs/data-format.md, evidence conventions). */
export function References({ references, owner }: ReferencesProps) {
  if (references.length === 0) return <p className="muted">No sources recorded yet.</p>;
  return (
    <ol className="references">
      {references.map((ref) => {
        const linkState = linkStateText(ref.check?.link);
        const found = ref.check ? checkSegments(ref.check) : [];
        return (
          <li key={ref.citation}>
            <span className="citation">{ref.citation}</span>
            {ref.supports && <span className="supports">{ref.supports}</span>}
            {ref.quote && <q className="quote">{ref.quote}</q>}
            {ref.proposed_by && (
              <span className="proposed-by">
                Proposed by an agent, run <code>{ref.proposed_by.run}</code> (see <code>{ref.proposed_by.summary}</code>)
              </span>
            )}
            <span className="reference-meta">
              {ref.status && <span className={`source-status source-${ref.status}`}>{STATUS_TEXT[ref.status]}</span>}
              {ref.doi && (
                <a href={`https://doi.org/${ref.doi}`} target="_blank" rel="noreferrer">
                  doi:{ref.doi}
                </a>
              )}
              {ref.url && (
                <span>
                  <a href={ref.url} target="_blank" rel="noreferrer">
                    link
                  </a>
                  {linkState && ` (${linkState})`}
                </span>
              )}
              <ReportLink
                text="Report"
                fact={owner.id}
                kind="reference"
                label={`${owner.label}: ${ref.citation}`}
                reference={ref.citation}
                run={ref.proposed_by?.run}
              />
            </span>
            {/* Where the work was found (ADR 0047): help for whoever reads it, never a verdict on the claim. */}
            {found.length > 0 && (
              <span className="reference-check">
                {found.map((segment, index) =>
                  "href" in segment ? (
                    <a key={index} href={segment.href} target="_blank" rel="noreferrer">
                      {segment.label}
                    </a>
                  ) : (
                    <span key={index}>{segment.text}</span>
                  ),
                )}
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
