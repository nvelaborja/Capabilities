import "maplibre-gl/dist/maplibre-gl.css";
import "./MapView.css";

import { type GeoJSONSource, Map as MapLibreMap, type MapGeoJSONFeature, NavigationControl, Popup, setWorkerUrl } from "maplibre-gl";
// MapLibre finds its web worker next to its own module, which bundling moves; Vite emits the worker file and gives its URL.
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import type { OccurrencesResponse, PlaceProperties } from "../api/types";
import { retrievedOn } from "../lib/dates";
import type { Theme } from "../state/theme";
import {
  bounds,
  emptyReason,
  placesUnder,
  recordLinkText,
  safeLink,
  sourceLine,
  stateText,
  whereText,
} from "./places";

// OpenFreeMap: free vector tiles from OpenStreetMap data, with no key and no cookies (ADR 0042). MapLibre adds the
// attribution the tiles carry.
const BASEMAPS: Record<Theme, string> = {
  light: "https://tiles.openfreemap.org/styles/positron",
  dark: "https://tiles.openfreemap.org/styles/dark",
};
const FONT = ["Noto Sans Regular"];

setWorkerUrl(workerUrl);

type Loaded = { status: "loading" } | { status: "ready"; value: OccurrencesResponse } | { status: "failed" };

interface MapViewProps {
  /** A material or a source. */
  id: string;
  theme: Theme;
  onClose: () => void;
}

/** Where a material or source is found, on a map: every mapped place of every source it comes from (ADR 0036). */
export function MapView({ id, theme, onClose }: MapViewProps) {
  const [places, setPlaces] = useState<Loaded>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    api
      .occurrences(id, controller.signal)
      .then((value) => setPlaces({ status: "ready", value }))
      .catch(() => {
        if (!controller.signal.aborted) setPlaces({ status: "failed" });
      });
    return () => controller.abort();
  }, [id]);

  const ready = places.status === "ready" ? places.value : null;
  return (
    <div className="map-view">
      {/* Keyed by theme: a new basemap style means a new map, and the places are added again. */}
      {ready && <PlacesMap key={theme} places={ready} theme={theme} />}
      <aside className="map-panel" aria-labelledby="map-title">
        <div className="map-panel-head">
          <h2 id="map-title">Where {ready ? ready.label.toLowerCase() : "it"} is found</h2>
          <button type="button" onClick={onClose}>
            Back to the graph
          </button>
        </div>
        {places.status === "loading" && <p className="muted">Loading places…</p>}
        {places.status === "failed" && <p className="error">Couldn't load the places.</p>}
        {ready && <Summary places={ready} />}
      </aside>
    </div>
  );
}

function Summary({ places }: { places: OccurrencesResponse }) {
  const empty = emptyReason(places);
  const haveData = places.datasets.length > 0;
  return (
    <>
      {places.sources.length > 0 && (
        <ul className="map-sources">
          {places.sources.map((source) => (
            <li key={source.id}>{sourceLine(source, haveData)}</li>
          ))}
        </ul>
      )}
      {empty && <p className="map-empty">{empty}</p>}
      {places.features.features.length > 0 && (
        // Open at first; closing it gives the map more room when the detail pane is open.
        <details className="map-key-details" open>
          <summary>Key and data source</summary>
          <ul className="map-legend" aria-label="Legend">
            <li>
              <span className="map-key map-key-worked" aria-hidden="true" /> Known to have been worked by a given year
            </li>
            <li>
              <span className="map-key map-key-present" aria-hidden="true" /> Present, with no known working date
            </li>
            <li>
              <span className="map-key map-key-cluster" aria-hidden="true" /> Several places: select to zoom in
            </li>
          </ul>
          <Datasets places={places} />
        </details>
      )}
    </>
  );
}

function Datasets({ places }: { places: OccurrencesResponse }) {
  return (
    <>
      {places.datasets.map((dataset) => (
        <p key={dataset.id} className="map-dataset">
          Places from{" "}
          {dataset.home ? (
            <a href={dataset.home} target="_blank" rel="noreferrer">
              {dataset.label}
            </a>
          ) : (
            dataset.label
          )}
          , retrieved {retrievedOn(dataset.retrieved_at)}. Modern records, most of them in the United States; a working
          year is the year production first began.
        </p>
      ))}
    </>
  );
}

/** Colours from theme.css, so the points match the graph's source nodes in either theme. */
function tokens() {
  const style = getComputedStyle(document.documentElement);
  const read = (name: string) => style.getPropertyValue(name).trim();
  return {
    fill: read("--type-source-fill"),
    line: read("--type-source-line"),
    ink: read("--type-source-ink"),
    surface: read("--surface"),
    text: read("--text"),
    backdrop: read("--backdrop"),
  };
}

type Colours = ReturnType<typeof tokens>;

const PLACE_LAYERS = ["places-worked", "places-present"];

function PlacesMap({ places, theme }: { places: OccurrencesResponse; theme: Theme }) {
  const container = useRef<HTMLDivElement>(null);
  const [basemapFailed, setBasemapFailed] = useState(false);

  useEffect(() => {
    if (!container.current) return;
    const colours = tokens();
    const box = bounds(places);
    const map = new MapLibreMap({
      container: container.current,
      style: BASEMAPS[theme],
      center: [0, 20],
      zoom: 1,
      ...(box ? { bounds: box, fitBoundsOptions: { padding: 48, maxZoom: 6 } } : {}),
    });
    map.addControl(new NavigationControl({ showCompass: false }), "bottom-right");

    // Without the basemap's style the map never loads, and the places would never be drawn. Fall back to a plain
    // background once, so the places still show offline or when OpenFreeMap is down.
    let styleArrived = false;
    map.once("styledata", () => (styleArrived = true));
    map.on("error", () => {
      if (styleArrived) return;
      styleArrived = true;
      setBasemapFailed(true);
      map.setStyle({
        version: 8,
        sources: {},
        layers: [{ id: "background", type: "background", paint: { "background-color": colours.backdrop } }],
      });
    });
    map.on("load", () => addPlaces(map, places, colours));

    map.on("click", "clusters", (event) => {
      const cluster = event.features?.[0];
      if (!cluster || cluster.geometry.type !== "Point") return;
      const center = cluster.geometry.coordinates as [number, number];
      const source = map.getSource<GeoJSONSource>("places");
      source
        ?.getClusterExpansionZoom(cluster.properties.cluster_id as number)
        .then((zoom) => map.easeTo({ center, zoom }))
        .catch(() => {});
    });
    // Every place under the pointer, not just the top one: places that share a spot never separate however far you zoom.
    map.on("click", PLACE_LAYERS, (event) => {
      const under = placesUnder(event.features ?? []);
      const first = under[0];
      if (!first || first.geometry.type !== "Point") return;
      new Popup({ maxWidth: "18rem" })
        .setLngLat(first.geometry.coordinates as [number, number])
        .setDOMContent(popupContent(under, places))
        .addTo(map);
    });
    // The pointer says what can be selected; selecting is a click or tap, never a hover (ADR 0019).
    for (const layer of ["clusters", ...PLACE_LAYERS]) {
      map.on("mouseenter", layer, () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", layer, () => (map.getCanvas().style.cursor = ""));
    }

    return () => map.remove();
  }, [places, theme]);

  return (
    <>
      <div ref={container} className="map-canvas" role="region" aria-label={`Map of where ${places.label.toLowerCase()} is found`} />
      {basemapFailed && (
        <p className="map-basemap-failed" role="status">
          The background map couldn't be loaded, so the places are drawn without it.
        </p>
      )}
    </>
  );
}

function addPlaces(map: MapLibreMap, places: OccurrencesResponse, colours: Colours) {
  map.addSource("places", {
    type: "geojson",
    data: places.features,
    cluster: true,
    clusterRadius: 40,
    clusterMaxZoom: 8,
  });
  map.addLayer({
    id: "clusters",
    type: "circle",
    source: "places",
    filter: ["has", "point_count"],
    paint: {
      "circle-color": colours.fill,
      "circle-opacity": 0.85,
      "circle-stroke-color": colours.line,
      "circle-stroke-width": 1.5,
      "circle-radius": ["step", ["get", "point_count"], 12, 25, 16, 250, 22, 1000, 28],
    },
  });
  // Text needs the basemap's fonts; on the plain fallback, a cluster's size still says roughly how many it holds.
  if (map.getStyle().glyphs) {
    map.addLayer({
      id: "cluster-count",
      type: "symbol",
      source: "places",
      filter: ["has", "point_count"],
      layout: { "text-field": ["get", "point_count_abbreviated"], "text-font": FONT, "text-size": 12 },
      paint: { "text-color": colours.ink },
    });
  }
  // Worked places are filled and present ones are rings, so the difference never rests on colour alone (ADR 0019).
  map.addLayer({
    id: "places-present",
    type: "circle",
    source: "places",
    filter: ["all", ["!", ["has", "point_count"]], ["!=", ["get", "state"], "worked"]],
    paint: {
      "circle-radius": 5,
      "circle-color": colours.surface,
      "circle-stroke-color": colours.line,
      "circle-stroke-width": 2.5,
    },
  });
  map.addLayer({
    id: "places-worked",
    type: "circle",
    source: "places",
    filter: ["all", ["!", ["has", "point_count"]], ["==", ["get", "state"], "worked"]],
    paint: {
      "circle-radius": 6,
      "circle-color": colours.fill,
      "circle-stroke-color": colours.text,
      "circle-stroke-width": 1.5,
    },
  });
}

/** The popup for the places under a click, built from text nodes: upstream names never become HTML. */
function popupContent(features: MapGeoJSONFeature[], places: OccurrencesResponse): HTMLElement {
  const root = document.createElement("div");
  root.className = "map-popup";
  if (features.length > 1) {
    const heading = document.createElement("strong");
    heading.className = "map-popup-count";
    heading.textContent = `${features.length} places here`;
    root.append(heading);
  }
  for (const feature of features) root.append(placeContent(feature.properties as PlaceProperties, places));
  return root;
}

function placeContent(place: PlaceProperties, places: OccurrencesResponse): HTMLElement {
  const root = document.createElement("div");
  root.className = "map-popup-place";
  const add = (tag: string, text: string, className?: string) => {
    const element = document.createElement(tag);
    element.textContent = text;
    if (className) element.className = className;
    root.append(element);
    return element;
  };
  add("strong", place.name || "Unnamed place");
  add("span", whereText(place), "map-popup-where");
  add("span", stateText({ state: place.state, worked_by_year: place.worked_by_year ?? null }), `map-popup-state map-popup-${place.state}`);
  const source = places.sources.find((summary) => summary.id === place.source_id);
  if (source && places.sources.length > 1) add("span", source.label);
  const details = [place.development_status && `Status: ${place.development_status}`, place.deposit_type && `Type: ${place.deposit_type}`];
  for (const detail of details.filter(Boolean)) add("span", detail as string, "map-popup-detail");
  const href = safeLink(place.url);
  if (href) {
    const link = add("a", recordLinkText(place.dataset, places.datasets));
    link.setAttribute("href", href);
    link.setAttribute("target", "_blank");
    link.setAttribute("rel", "noreferrer");
  }
  return root;
}
