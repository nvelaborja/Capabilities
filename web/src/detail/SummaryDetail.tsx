import { NodeChip } from "../chips/NodeChip";
import type { Summary } from "../graph/summaries";
import { LIMIT, noun } from "../lib/bounded";
import { DetailShell } from "./DetailShell";
import type { DetailContext } from "./NodeDetail";

interface SummaryDetailProps extends DetailContext {
  summary: Summary | undefined;
  onExpand: (summary: Summary) => void;
}

/** A summary node ("Heat → 4 more materials"): what it stands for, and a way to show its links (ADR 0024). */
export function SummaryDetail({ summary, catalog, explore, crumbs, onBack, onDrill, onClose, onExpand }: SummaryDetailProps) {
  if (!summary) {
    return (
      <DetailShell label="Summary" crumbs={crumbs} onBack={onBack} onClose={onClose} title="Summary">
        <p className="muted">These links are already showing on the graph.</p>
      </DetailShell>
    );
  }
  const hub = catalog.get(summary.hub);
  const things = noun(summary.kind, summary.members.length);
  const linked = summary.direction === "out" ? `that ${hub.label.toLowerCase()} helps make` : `that ${hub.label.toLowerCase()} needs`;
  return (
    <DetailShell
      label={summary.label}
      crumbs={crumbs}
      onBack={onBack}
      onClose={onClose}
      title={summary.label}
      actions={
        <button type="button" className="primary" onClick={() => onExpand(summary)}>
          Show these {summary.members.length} links
        </button>
      }
    >
      <section className="detail-column" aria-labelledby="summary-why">
        <h3 id="summary-why">Why it's folded</h3>
        <p>
          <NodeChip id={summary.hub} label={hub.label} kind={hub.kind} status={explore?.status[summary.hub]} onPick={onDrill} /> links to
          many things. To keep the graph readable, it shows only its {LIMIT} most advanced links in each direction.
        </p>
        <p className="muted">
          These {summary.members.length} {things} are still on the graph, in their own columns; only their lines to {hub.label.toLowerCase()} are
          folded into this node.
        </p>
      </section>
      <section className="detail-column" aria-labelledby="summary-members">
        <h3 id="summary-members">
          The {summary.members.length} {things} {linked}
        </h3>
        <ul className="chip-row">
          {summary.members.map((id) => {
            const entry = catalog.get(id);
            return (
              <li key={id}>
                <NodeChip id={id} label={entry.label} kind={entry.kind} status={explore?.status[id]} onPick={onDrill} />
              </li>
            );
          })}
        </ul>
      </section>
      <section className="detail-column" aria-labelledby="summary-show">
        <h3 id="summary-show">Show them</h3>
        <p>
          <strong>Show these {summary.members.length} links</strong> draws their lines to {hub.label.toLowerCase()} and removes this summary.
        </p>
        <p className="muted">“Expand all” in the graph toolbar shows every folded link at once.</p>
      </section>
    </DetailShell>
  );
}
