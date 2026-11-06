import type { ExploreResponse, Profile } from "../api/types";
import type { Catalog } from "../catalog";
import { CapabilityList } from "./CapabilityList";
import { selectedChips, withinReach } from "./groups";
import { PresetPicker } from "./PresetPicker";
import "./panes.css";

interface SidePaneProps {
  profiles: Profile[];
  preset: string | null;
  edited: boolean;
  explore: ExploreResponse | null;
  catalog: Catalog;
  onChoosePreset: (preset: string | null) => void;
  onClear: () => void;
  onRemove: (id: string) => void;
  onPick: (id: string) => void;
}

/**
 * The right-hand pane: preset on top, then what was chosen, then everything that follows from it (implied, could
 * make, could do, one step away), each half scrolling on its own (ADR 0017, 0025).
 */
export function SidePane({ profiles, preset, edited, explore, catalog, onChoosePreset, onClear, onRemove, onPick }: SidePaneProps) {
  const chosen = explore ? selectedChips(explore, catalog) : [];
  const following = explore ? withinReach(explore, catalog) : [];

  return (
    <aside className="side-pane" aria-label="Selection">
      <PresetPicker profiles={profiles} preset={preset} edited={edited} onChoose={onChoosePreset} />
      {explore && explore.warnings.length > 0 && (
        <ul className="warnings" aria-label="Warnings">
          {explore.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}
      <CapabilityList
        id="selected"
        title="Selected"
        sections={chosen.length > 0 ? [{ key: "chosen", title: "", chips: chosen }] : []}
        emptyText="Nothing selected. Pick a preset, or click a node on the graph and add it."
        onPick={onPick}
        onRemove={onRemove}
        headerAction={
          chosen.length > 0 && (
            <button type="button" className="link-button" onClick={onClear}>
              Clear all
            </button>
          )
        }
      />
      <CapabilityList
        id="reach"
        title="Implied and reachable"
        sections={following}
        emptyText="Nothing follows from the selection yet."
        onPick={onPick}
      />
    </aside>
  );
}
