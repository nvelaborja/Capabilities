import cytoscape, { type Core, type EdgeSingular, type NodeSingular } from "cytoscape";
import { type ReactNode, useEffect, useRef, useState } from "react";

import type { ExploreResponse, GraphResponse } from "../api/types";
import type { Theme } from "../state/theme";
import { toElements } from "./elements";
import { applyFolding, unfoldAll } from "./fold";
import { parseSubject } from "../detail/subjects";
import { clearFocus, findEdge, focusOn, focusOnEdge, isolate, OUTSIDE } from "./focus";
import "./GraphView.css";
import { READABLE_ZOOM, runLayout, showInitialView } from "./layout";
import { applyStatuses } from "./statuses";
import { buildStylesheet, readTokens } from "./styles";

const ZOOM_STEP = 1.25;
const PADDING = 24;

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
  /** Focus mode: show only this node, what it certainly needs, and what it directly makes. */
  isolated: string | null;
  /** Called with a node's id when it is clicked, or null when the background is. */
  onSelectNode: (id: string | null) => void;
  /** Called when a line is clicked, with the nodes it joins. */
  onSelectEdge: (source: string, target: string) => void;
  onShowWholeGraph: () => void;
  /** More toolbar items after the graph's own buttons (the legend). */
  toolbarExtra?: ReactNode;
}

/** The node or line the detail pane is showing, if it is on the graph. */
function focusedElement(cy: Core, id: string | null): NodeSingular | EdgeSingular | null {
  if (!id) return null;
  const subject = parseSubject(id);
  if (subject.type === "edge") return findEdge(cy, subject.source, subject.target);
  const node = cy.getElementById(subject.id);
  return node.nonempty() && node.isNode() ? node : null;
}

function isInView(cy: Core, box: { x1: number; x2: number; y1: number; y2: number }): boolean {
  const view = cy.extent();
  return box.x1 >= view.x1 && box.x2 <= view.x2 && box.y1 >= view.y1 && box.y2 <= view.y2;
}

export function GraphView(props: GraphViewProps) {
  const { graph, explore, theme, focus, isolated, onSelectNode, onSelectEdge, onShowWholeGraph, toolbarExtra } = props;
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const exploreRef = useRef<ExploreResponse | null>(explore);
  const onSelectRef = useRef(onSelectNode);
  const onSelectEdgeRef = useRef(onSelectEdge);
  const focusIdRef = useRef<string | null>(focus.id);
  // The first view after building the graph frames the selection; later re-layouts keep the user's place.
  const freshRef = useRef(true);
  const [expandAll, setExpandAll] = useState(false);

  useEffect(() => {
    onSelectRef.current = onSelectNode;
    onSelectEdgeRef.current = onSelectEdge;
  }, [onSelectNode, onSelectEdge]);

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
    cy.on("tap", "node", (event) => {
      const node = event.target;
      if (!node.hasClass("level-label")) onSelectRef.current(node.id());
    });
    cy.on("tap", "edge", (event) => {
      const edge = event.target;
      onSelectEdgeRef.current(edge.source().id(), edge.target().id());
    });
    cy.on("tap", (event) => {
      if (event.target === cy) onSelectRef.current(null);
    });

    // The canvas narrows when the detail pane opens. Keep nodes where they were on screen, and keep the focused node
    // in view, rather than letting everything slide sideways.
    let left = container.getBoundingClientRect().left;
    const observer = new ResizeObserver(() => {
      const nowLeft = container.getBoundingClientRect().left;
      cy.resize();
      cy.panBy({ x: left - nowLeft, y: 0 });
      left = nowLeft;
      const focused = focusedElement(cy, focusIdRef.current);
      if (focused && !isInView(cy, focused.boundingBox())) cy.center(focused);
    });
    observer.observe(container);

    cyRef.current = cy;
    freshRef.current = true;
    return () => {
      observer.disconnect();
      cyRef.current = null;
      cy.destroy();
    };
  }, [graph]);

  // What is showing: focus mode, then busy nodes' extra lines folded among what remains (ADR 0030), then the columns.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    isolate(cy, isolated, isolated ? (graph.needs[isolated] ?? []) : []);
    if (expandAll) unfoldAll(cy);
    else applyFolding(cy);
    runLayout(cy);
    applyStatuses(cy, exploreRef.current);
    const showing = cy.nodes().not(`.${OUTSIDE}`);
    if (isolated) {
      cy.fit(showing, PADDING);
      if (cy.zoom() > READABLE_ZOOM * 1.5) cy.zoom(READABLE_ZOOM * 1.5);
      cy.center(showing);
    } else if (freshRef.current) {
      showInitialView(cy, cy.nodes(".status-selected"));
    } else {
      const anchor = focusIdRef.current ? cy.getElementById(focusIdRef.current) : null;
      if (anchor?.nonempty()) {
        cy.zoom(Math.max(cy.zoom(), READABLE_ZOOM));
        cy.center(anchor);
      }
    }
    freshRef.current = false;
  }, [graph, isolated, expandAll]);

  useEffect(() => {
    cyRef.current?.style(buildStylesheet(readTokens()));
  }, [theme]);

  useEffect(() => {
    focusIdRef.current = focus.id;
    const cy = cyRef.current;
    if (!cy) return;
    const target = focusedElement(cy, focus.id);
    if (!target) {
      clearFocus(cy);
      return;
    }
    if (target.isEdge()) focusOnEdge(target);
    else focusOn(target);
    if (focus.center && !target.hasClass(OUTSIDE)) {
      cy.animate({ center: { eles: target }, zoom: Math.max(cy.zoom(), READABLE_ZOOM) }, { duration: 250 });
    }
  }, [focus, graph, isolated, expandAll]);

  const zoomBy = (factor: number) => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.zoom({ level: cy.zoom() * factor, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
  };

  const isolatedLabel = isolated ? (graph.nodes.find((node) => node.id === isolated)?.label ?? isolated) : null;

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
        <button type="button" onClick={() => cyRef.current?.fit(cyRef.current.nodes().not(`.${OUTSIDE}`), PADDING)} title="Fit the whole graph">
          Fit
        </button>
        <button
          type="button"
          aria-pressed={expandAll}
          onClick={() => setExpandAll((value) => !value)}
          title={expandAll ? "Hide busy nodes' extra lines again" : "Draw every line, including busy nodes' extra lines"}
        >
          {expandAll ? "Fewer lines" : "Expand all"}
        </button>
        {toolbarExtra}
      </div>
      {isolatedLabel && (
        <div className="graph-banner" role="status">
          <span>
            Focus: what <strong>{isolatedLabel}</strong> certainly needs, and what it leads to.
          </span>
          <button type="button" onClick={onShowWholeGraph}>
            Show whole graph
          </button>
        </div>
      )}
    </div>
  );
}
