import type { ReactNode } from "react";

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
  /** The gap between the two panes, which resizes them. */
  splitter: ReactNode;
}

/**
 * The right-hand column, as two panes (ADR 0029): the preset and what was chosen on top, sized to fit up to half the
 * column, and everything that follows from it (implied, could make, could do, one step away) below. Each scrolls on
 * its own, and the gap between them resizes them.
 */
export function SidePane(props: SidePaneProps) {
  const { profiles, preset, edited, explore, catalog, onChoosePreset, onClear, onRemove, onPick, splitter } = props;
  const chosen = explore ? selectedChips(explore, catalog) : [];
  const following = explore ? withinReach(explore, catalog) : [];

  return (
    <div className="side-column">
      <aside className="selection-pane" aria-label="Selection">
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
      </aside>
      {splitter}
      <aside className="reach-pane" aria-label="Implied and reachable">
        <CapabilityList
          id="reach"
          title="Implied and reachable"
          sections={following}
          emptyText="Nothing follows from the selection yet."
          onPick={onPick}
        />
      </aside>
    </div>
  );
}
