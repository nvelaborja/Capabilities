import cytoscape, { type Core } from "cytoscape";
import { useEffect, useRef } from "react";

import type { ExploreResponse, GraphResponse } from "../api/types";
import type { Theme } from "../state/theme";
import { toElements } from "./elements";
import { clearFocus, focusOn } from "./focus";
import "./GraphView.css";
import { runLayout, showInitialView } from "./layout";
import { applyStatuses } from "./statuses";
import { buildStylesheet, readTokens } from "./styles";

const ZOOM_STEP = 1.25;

interface GraphViewProps {
  graph: GraphResponse;
  explore: ExploreResponse | null;
  /** The theme showing; the graph re-reads its colours from theme.css when it changes. */
  theme: Theme;
}

export function GraphView({ graph, explore, theme }: GraphViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const exploreRef = useRef<ExploreResponse | null>(explore);

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
      if (!event.target.hasClass("level-label")) focusOn(event.target);
    });
    cy.on("tap", (event) => {
      if (event.target === cy) clearFocus(cy);
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
