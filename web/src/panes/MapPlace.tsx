import type { ExploreResponse, ProfileMap, ProfileSource } from "../api/types";
import { NodeChip } from "../chips/NodeChip";
import { bordersLine, countsLine, placeLine, sourceNote, sourcesByAvailability, sourceTitle } from "./profilePlace";

interface MapPlaceProps {
  place: ProfileMap;
  explore: ExploreResponse | null;
  onPick: (id: string) => void;
}

/**
 * Where the preset is, and the sources found in its area (ADR 0052): those worked by its last year are had, and added
 * to the selection; the rest are maybes, shown and never assumed.
 */
export function MapPlace({ place, explore, onPick }: MapPlaceProps) {
  const { had, maybe } = sourcesByAvailability(place);
  const last = place.years[1];
  const chips = (sources: ProfileSource[]) => (
    <ul className="chip-row">
      {sources.map((source) => (
        <li key={source.id}>
          <NodeChip
            id={source.id}
            label={source.label}
            kind={source.kind}
            status={explore?.status[source.id]}
            note={sourceNote(source, last)}
            title={sourceTitle(source) || undefined}
            onPick={onPick}
          />
        </li>
      ))}
    </ul>
  );
  return (
    // Folded at first, so the selection below stays in view; the summary still says what the map found.
    <details className="map-place">
      <summary>
        <span className="map-place-title">From the map</span> <span className="map-place-counts">{countsLine(place)}</span>
      </summary>
      <p className="map-place-where">{placeLine(place)}</p>
      <p className="map-place-borders">{bordersLine(place)}</p>
      {place.sources.length === 0 && <p className="empty">No mapped mine, quarry or deposit is inside the area.</p>}
      {had.length > 0 && (
        <div className="chip-section" aria-label="Had">
          <h3>Had · worked there by then</h3>
          {chips(had)}
        </div>
      )}
      {maybe.length > 0 && (
        <div className="chip-section" aria-label="Maybe">
          <h3>Maybe · there, not known to be worked by then</h3>
          {chips(maybe)}
        </div>
      )}
    </details>
  );
}
