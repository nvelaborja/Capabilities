import type { ReactNode } from "react";

import { byKind, countChips, type Section } from "./groups";
import { NodeChip } from "../chips/NodeChip";

interface CapabilityListProps {
  id: string;
  title: string;
  sections: Section[];
  emptyText: string;
  onPick: (id: string) => void;
  onRemove?: (id: string) => void;
  headerAction?: ReactNode;
}

/** A titled, independently scrolling set of chips, each type starting on its own line. */
export function CapabilityList({ id, title, sections, emptyText, onPick, onRemove, headerAction }: CapabilityListProps) {
  return (
    <section className="capability-list" aria-labelledby={`${id}-title`}>
      <header className="capability-header">
        <h2 id={`${id}-title`}>
          {title} <span className="count">{countChips(sections)}</span>
        </h2>
        {headerAction}
      </header>
      <div className="capability-scroll">
        {sections.length === 0 && <p className="empty">{emptyText}</p>}
        {sections.map((section) => (
          <div key={section.key} className="chip-section" aria-label={section.title || title}>
            {section.title && (
              <h3>
                {section.title} <span className="count">{section.chips.length}</span>
                {section.hint && <span className="section-hint"> · {section.hint}</span>}
              </h3>
            )}
            {byKind(section.chips).map((run) => (
              <ul key={run[0]?.kind} className="chip-row">
                {run.map((chip) => (
                  <li key={chip.id}>
                    <NodeChip {...chip} onPick={onPick} onRemove={chip.removable ? onRemove : undefined} />
                  </li>
                ))}
              </ul>
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}
