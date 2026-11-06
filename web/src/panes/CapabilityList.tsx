import { type ReactNode, useState } from "react";

import { byKind, type Chip, type ChipGroup, countChips, type Section, sectionCount } from "./groups";
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
                {section.title} <span className="count">{sectionCount(section)}</span>
                {section.hint && <span className="section-hint"> · {section.hint}</span>}
              </h3>
            )}
            {section.groups?.map((group) => <FoldedChips key={group.key} group={group} onPick={onPick} />)}
            {byKind(section.chips).map((run) => (
              <ChipRow key={run[0]?.kind} chips={run} onPick={onPick} onRemove={onRemove} />
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}

function ChipRow({ chips, onPick, onRemove }: { chips: Chip[]; onPick: (id: string) => void; onRemove?: (id: string) => void }) {
  return (
    <ul className="chip-row">
      {chips.map((chip) => (
        <li key={chip.id}>
          <NodeChip {...chip} onPick={onPick} onRemove={chip.removable ? onRemove : undefined} />
        </li>
      ))}
    </ul>
  );
}

/** One chip standing for many ("Cut · 19 materials"); clicking it shows or hides them, on the lines below. */
function FoldedChips({ group, onPick }: { group: ChipGroup; onPick: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="chip-group">
      <NodeChip
        id={group.key}
        label={group.label}
        kind={group.kind}
        status={group.status}
        note={group.note}
        expanded={open}
        onPick={() => setOpen((value) => !value)}
      />
      {open && (
        <div className="chip-group-items">
          <ChipRow chips={group.chips} onPick={onPick} />
        </div>
      )}
    </div>
  );
}
