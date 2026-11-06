import type { ExploreResponse, SelectionRequest } from "../api/types";
import type { Catalog } from "../catalog";
import type { Summary } from "../graph/summaries";
import type { Trail } from "../state/trail";
import "./detail.css";
import { EdgeDetail } from "./EdgeDetail";
import { NodeDetail } from "./NodeDetail";
import { parseSubject } from "./subjects";
import { SummaryDetail } from "./SummaryDetail";

interface DetailPaneProps {
  trail: Trail;
  catalog: Catalog;
  explore: ExploreResponse | null;
  selection: SelectionRequest;
  isolated: string | null;
  summaries: readonly Summary[];
  onDrill: (id: string) => void;
  onBack: (index: number) => void;
  onClose: () => void;
  onAdd: (id: string) => void;
  onRemove: (id: string) => void;
  onIsolate: (id: string | null) => void;
  onExpandSummary: (summary: Summary) => void;
}

/** The pane under the graph (ADR 0025): a node, a line, or a summary node, whichever was clicked last. */
export function DetailPane(props: DetailPaneProps) {
  const { trail, catalog, summaries } = props;
  const id = trail.at(-1);
  if (!id) return null;

  const label = (crumb: string) => {
    const subject = parseSubject(crumb);
    if (subject.type === "edge") return `${catalog.get(subject.source).label} → ${catalog.get(subject.target).label}`;
    if (subject.type === "summary") return summaries.find((s) => s.id === crumb)?.label ?? "Summary";
    return catalog.get(subject.id).label;
  };
  const context = {
    catalog,
    explore: props.explore,
    selection: props.selection,
    crumbs: trail.slice(0, -1).map((crumb) => ({ id: crumb, label: label(crumb) })),
    onBack: props.onBack,
    onDrill: props.onDrill,
    onClose: props.onClose,
  };

  const subject = parseSubject(id);
  // Keyed by subject, so lists and dialogs start fresh for each one.
  switch (subject.type) {
    case "edge":
      return <EdgeDetail key={id} {...context} source={subject.source} target={subject.target} />;
    case "summary":
      return <SummaryDetail key={id} {...context} summary={summaries.find((s) => s.id === id)} onExpand={props.onExpandSummary} />;
    case "node":
      return (
        <NodeDetail
          key={id}
          {...context}
          id={subject.id}
          isolated={props.isolated}
          onAdd={props.onAdd}
          onRemove={props.onRemove}
          onIsolate={props.onIsolate}
        />
      );
  }
}
