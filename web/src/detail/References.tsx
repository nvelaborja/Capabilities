import type { Reference } from "../api/types";

const STATUS_TEXT: Record<NonNullable<Reference["status"]>, string> = {
  verified: "verified",
  secondary: "from a summary",
  unverified: "not yet checked",
};

/** Where a claim comes from, and how carefully it was checked (docs/data-format.md, evidence conventions). */
export function References({ references }: { references: readonly Reference[] }) {
  if (references.length === 0) return <p className="muted">No sources recorded yet.</p>;
  return (
    <ol className="references">
      {references.map((ref) => (
        <li key={ref.citation}>
          <span className="citation">{ref.citation}</span>
          {ref.supports && <span className="supports">{ref.supports}</span>}
          <span className="reference-meta">
            {ref.status && <span className={`source-status source-${ref.status}`}>{STATUS_TEXT[ref.status]}</span>}
            {ref.doi && (
              <a href={`https://doi.org/${ref.doi}`} target="_blank" rel="noreferrer">
                doi:{ref.doi}
              </a>
            )}
            {ref.url && (
              <a href={ref.url} target="_blank" rel="noreferrer">
                link
              </a>
            )}
          </span>
        </li>
      ))}
    </ol>
  );
}
