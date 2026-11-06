import type { ItemRow, LeadsToRow } from "../api/types";
import { NodeChip } from "../chips/NodeChip";
import { BoundedList } from "./BoundedList";

/** A ranked list of items as chips, bounded to the top N with the rest summarised by type (ADR 0020). */
export function ItemChips({ items, onDrill }: { items: readonly (ItemRow | LeadsToRow)[]; onDrill: (id: string) => void }) {
  return (
    <BoundedList
      className="item-chips"
      items={items}
      kindOf={(item) => item.kind}
      keyOf={(item) => item.id}
      render={(item) => (
        <li className="item">
          <NodeChip id={item.id} label={item.label} kind={item.kind} status={item.status} onPick={onDrill} />
          {"via" in item && <span className="via">via {item.via.join(" or ").toLowerCase()}</span>}
        </li>
      )}
    />
  );
}
