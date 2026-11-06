import type { ExploreResponse, Profile } from "../api/types";
import type { Catalog } from "../catalog";
import { CapabilityList } from "./CapabilityList";
import { reachableGroups, selectedGroups } from "./groups";
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

/** The right-hand pane: preset on top, then Selected and Reachable, each scrolling on its own (ADR 0017). */
export function SidePane({ profiles, preset, edited, explore, catalog, onChoosePreset, onClear, onRemove, onPick }: SidePaneProps) {
  const selected = explore ? selectedGroups(explore, catalog) : [];
  const reachable = explore ? reachableGroups(explore, catalog) : [];
  const near = explore?.near ?? [];
  const hasSelection = (explore?.selected.length ?? 0) > 0;

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
        groups={selected}
        emptyText="Nothing selected. Pick a preset, or click a node on the graph and add it."
        onPick={onPick}
        onRemove={onRemove}
        headerAction={
          hasSelection && (
            <button type="button" className="link-button" onClick={onClear}>
              Clear all
            </button>
          )
        }
      />
      <CapabilityList
        id="reachable"
        title="Reachable"
        groups={reachable}
        emptyText="Nothing else is within reach yet."
        onPick={onPick}
      >
        {near.length > 0 && (
          <details open className="group near">
            <summary>
              One step away <span className="count">{near.length}</span>
            </summary>
            <ul>
              {near.map((item) => (
                <li key={item.id} className="row">
                  <button type="button" className="row-label" onClick={() => onPick(item.id)}>
                    {item.label}
                  </button>
                  <span className="row-note">
                    Missing {[...new Set(item.routes.map((route) => route.missing.label.toLowerCase()))].join(" or ")}
                  </span>
                </li>
              ))}
            </ul>
          </details>
        )}
      </CapabilityList>
    </aside>
  );
}
