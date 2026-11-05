import cytoscape, { type Core } from "cytoscape";
import { useEffect, useRef } from "react";

import type { ExploreResponse, GraphResponse } from "../api/types";
import type { Theme } from "../state/theme";
import { toElements } from "./elements";
import { clearFocus, focusOn } from "./focus";
import "./GraphView.css";
import { READABLE_ZOOM, runLayout, showInitialView } from "./layout";
import { applyStatuses } from "./statuses";
import { buildStylesheet, readTokens } from "./styles";

const ZOOM_STEP = 1.25;

/** Which node is focused. `seq` changes on every request, so asking for the same node again re-centres it. */
export interface GraphFocus {
  id: string | null;
  center: boolean;
  seq: number;
}

interface GraphViewProps {
  graph: GraphResponse;
  explore: ExploreResponse | null;
  /** The theme showing; the graph re-reads its colours from theme.css when it changes. */
  theme: Theme;
  focus: GraphFocus;
  /** Called with a node's id when it is clicked, or null when the background is. */
  onSelectNode: (id: string | null) => void;
}

export function GraphView({ graph, explore, theme, focus, onSelectNode }: GraphViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const exploreRef = useRef<ExploreResponse | null>(explore);
  const onSelectRef = useRef(onSelectNode);

  useEffect(() => {
    onSelectRef.current = onSelectNode;
  }, [onSelectNode]);

  // Declared before the graph effect so a freshly built graph picks up the latest statuses.
  useEffect(() => {
    exploreRef.current = explore;
    if (cyRef.current) applyStatuses(cyRef.current, explore);
  }, [explore]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const cy = cytoscape({
      container,
      elements: toElements(graph),
      style: buildStylesheet(readTokens()),
      minZoom: 0.08,
      maxZoom: 3,
      boxSelectionEnabled: false,
      autoungrabify: true,
    });
    runLayout(cy);
    applyStatuses(cy, exploreRef.current);
    showInitialView(cy, cy.nodes(".status-selected"));
    cy.on("tap", "node", (event) => {
      if (!event.target.hasClass("level-label")) onSelectRef.current(event.target.id());
    });
    cy.on("tap", (event) => {
      if (event.target === cy) onSelectRef.current(null);
    });

    cyRef.current = cy;
    return () => {
      cyRef.current = null;
      cy.destroy();
    };
  }, [graph]);

  useEffect(() => {
    cyRef.current?.style(buildStylesheet(readTokens()));
  }, [theme]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    const node = focus.id ? cy.getElementById(focus.id) : null;
    if (!node || node.empty()) {
      clearFocus(cy);
      return;
    }
    focusOn(node);
    if (focus.center) {
      cy.animate({ center: { eles: node }, zoom: Math.max(cy.zoom(), READABLE_ZOOM) }, { duration: 250 });
    }
  }, [focus, graph]);

  const zoomBy = (factor: number) => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.zoom({ level: cy.zoom() * factor, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
  };

  return (
    <div className="graph-view">
      <div ref={containerRef} className="graph-canvas" role="region" aria-label="Capabilities graph" data-testid="graph" />
      <div className="graph-toolbar" role="toolbar" aria-label="Graph view">
        <button type="button" onClick={() => zoomBy(ZOOM_STEP)} aria-label="Zoom in" title="Zoom in">
          +
        </button>
        <button type="button" onClick={() => zoomBy(1 / ZOOM_STEP)} aria-label="Zoom out" title="Zoom out">
          −
        </button>
        <button type="button" onClick={() => cyRef.current?.fit(undefined, 24)} title="Fit the whole graph">
          Fit
        </button>
      </div>
    </div>
  );
}
