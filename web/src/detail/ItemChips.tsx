import type { ItemRow, LeadsToRow } from "../api/types";
import { NodeChip } from "../chips/NodeChip";
import { BoundedList } from "./BoundedList";

/** A one-click way to select each item, for a class's members (ADR 0031). */
export interface QuickAdd {
  isChosen: (id: string) => boolean;
  onAdd: (id: string) => void;
}

interface ItemChipsProps {
  items: readonly (ItemRow | LeadsToRow)[];
  onDrill: (id: string) => void;
  quickAdd?: QuickAdd;
}

/** A ranked list of items as chips, bounded to the top N with the rest summarised by type (ADR 0020). */
export function ItemChips({ items, onDrill, quickAdd }: ItemChipsProps) {
  return (
    <BoundedList
      className="item-chips"
      items={items}
      kindOf={(item) => item.kind}
      keyOf={(item) => item.id}
      render={(item) => (
        <li className="item">
          <NodeChip id={item.id} label={item.label} kind={item.kind} status={item.status} onPick={onDrill} />
          {quickAdd && <AddButton item={item} quickAdd={quickAdd} />}
          {"via" in item && <span className="via">via {item.via.join(" or ").toLowerCase()}</span>}
        </li>
      )}
    />
  );
}

function AddButton({ item, quickAdd }: { item: ItemRow; quickAdd: QuickAdd }) {
  if (quickAdd.isChosen(item.id)) return <span className="quick-added">✓ Selected</span>;
  return (
    <button type="button" className="quick-add" onClick={() => quickAdd.onAdd(item.id)} aria-label={`Add ${item.label} to selected`}>
      + Add
    </button>
  );
}
