# MapLibre GL JS and OpenFreeMap

## What it is

**MapLibre GL JS** is a JavaScript library that draws interactive maps in the browser with WebGL. It began in 2020 as the open-source continuation of Mapbox GL JS, after Mapbox changed that library's license. It draws **vector tiles**, so the map is rendered on your machine from data rather than downloaded as pictures. That makes it sharp at any zoom, and the same data can be restyled, for example for a dark theme.

**OpenFreeMap** is a free public tile server for MapLibre. It serves vector tiles of OpenStreetMap data and ready-made styles, with no API key and no cookies.

## How it works

**Tiles.** The world is cut into square tiles, at each zoom level `z` a grid of 2^z × 2^z of them, addressed `{z}/{x}/{y}`. A map shows only the tiles covering the screen at the current zoom. *Raster* tiles are images; *vector* tiles hold geometry and attributes (roads, borders, place names) in a compact binary format (Mapbox Vector Tiles, `.pbf`), which the browser draws itself.

**Styles.** A style is a JSON document (the MapLibre Style Specification). It lists *sources*, which say where data comes from (a tile server, or GeoJSON), and *layers*, which say what to draw from each source and how, in order. A layer has a `type` (`fill`, `line`, `circle`, `symbol` for text and icons…), an optional `filter`, and `paint` and `layout` properties. Fonts (*glyphs*) and icons (*sprites*) are fetched from URLs the style names. Loading a basemap is just pointing the map at a style URL.

**Expressions.** Property values and filters can be expressions, small programs in JSON arrays evaluated per feature: `["get", "state"]` reads a property, `["==", ["get", "state"], "worked"]` compares, `["step", ["get", "point_count"], 12, 25, 16]` picks a value by threshold. Expressions are how one layer draws thousands of features differently without any JavaScript per feature.

**GeoJSON sources and clustering.** Your own data can be added as a GeoJSON source (RFC 7946: a `FeatureCollection` of features, each with a `geometry` and `properties`; coordinates are longitude, then latitude). With `cluster: true`, MapLibre groups nearby points at each zoom into clusters with a `point_count`, and `clusterProperties` can add up other values per cluster. `getClusterExpansionZoom` says how far to zoom for a cluster to split.

**Web workers.** Parsing tiles and clustering run in background web workers, so the page stays responsive. The worker is a separate script that MapLibre must be able to load. A bundler that moves MapLibre's code needs to emit that script and tell MapLibre where it is (`setWorkerUrl`).

**Events and popups.** `map.on("click", "layer-id", handler)` gives the features under the pointer in that layer; pass a list of layer ids to hear several layers in one handler. A `Popup` is a small box anchored to a coordinate, filled with HTML or a DOM element.

**Loading and errors.** The map fires `load` once its style and the first tiles are in, and `error` when something can't be fetched. If the style itself fails, `load` never fires, so anything added in a `load` handler never appears unless the map is given another style (`setStyle`).

**Attribution.** Map data comes with credit requirements. OpenStreetMap's data is under the ODbL and must be credited. MapLibre shows the attribution the tiles carry in a control in the corner.

## How we use it

The map shows where a material or source is found ([ADR 0042](../../adr/0042-show-where-things-are-found-on-a-maplibre-map.md), [ADR 0036](../../adr/0036-place-sources-and-profiles-in-space-and-time.md)):

1. In the detail pane, **Where it's found** (on a source, or a material extracted from one) replaces the graph with the map.
2. The web app fetches `GET /api/occurrences/{id}`: a summary of each source, the datasets, and every place as GeoJSON ([data pipeline](../data-pipeline.md#who-reads-what)).
3. `MapView` creates a map over OpenFreeMap's `positron` (light) or `dark` style, adds the places as a clustered GeoJSON source, and draws four layers:
   - clusters, with counts;
   - places known to have been worked, as filled dots;
   - places present with no known working date, as rings;
   - the cluster labels.
4. Selecting a cluster zooms in. Selecting a place opens a popup with its name, location, state in words, MRDS status and type, and a link to its record in its dataset. When several places are under the pointer, as when they share coordinates, the popup lists them all.

The panel over the map has one line per source, a key and the data source. It also explains an empty map: a material that is made, a source found almost everywhere, a source with no mapped places (with its curated regions instead), or no snapshot downloaded.

Why MapLibre: it is the open (BSD-3-Clause) standard for vector maps on the web, it draws thousands of points on the GPU, and its styles follow our light and dark themes. Why OpenFreeMap: free, no key, no cookies, no limits. The trade-off is that the browser talks to a third party when the map opens ([ADR 0042](../../adr/0042-show-where-things-are-found-on-a-maplibre-map.md) lists the alternatives).

## Where it lives

| What | Where |
|---|---|
| The map component (lazy-loaded) | `web/src/map/MapView.tsx`, `MapView.css` |
| Text, bounds and which nodes can be mapped (tested) | `web/src/map/places.ts`, `places.test.ts` |
| The button and the switch between graph and map | `web/src/detail/NodeDetail.tsx`, `web/src/App.tsx` |
| The API that feeds it | `GET /api/occurrences/{id}` in `packages/api/src/capabilities_api/server.py`; `packages/core/src/capabilities/places.py` |

```bash
uv run capabilities serve                      # then open a material such as Hematite, and "Where it's found"
curl -s localhost:8000/api/occurrences/hematite | python3 -m json.tool | head -40
```

## Things to know

- **Coordinates are longitude first**, in GeoJSON and everywhere in MapLibre.
- **Colours come from `theme.css`.** `MapView` reads the CSS custom properties when the map is created. Changing the theme makes a new map, because a new basemap style replaces every layer.
- **Shape, not colour, tells worked from present** (filled dot or ring), and the popup says it in words ([ADR 0019](../../adr/0019-desktop-first-mobile-ready.md)). Popups open on click or tap, never on hover.
- **Upstream text is never HTML.** Popups are built from text nodes, because names come from a dataset we don't control. For the same reason a record link is followed only if it is http or https (`safeLink` in `places.ts`).
- **Without the basemap, the places still draw.** If OpenFreeMap's style can't be loaded (offline, blocked, or down), `MapView` switches to a one-layer style with a plain background and says so on the map. That style has no fonts, so clusters show no counts.
- **Places can share coordinates.** Clustering never separates them, so the place click handler takes every feature under the pointer (`placesUnder`), not just the first.
- **MapLibre draws on animation frames.** In a hidden or background browser tab it draws nothing, which matters for automated screenshots, not for people.
- **The worker must be bundled.** `import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url"` and `setWorkerUrl(workerUrl)`. Without them the console says "Worker failed to load" and the map stays blank.
- **Keep the attribution control.** It is a condition of OpenStreetMap's license.

## Further reading

1. [MapLibre GL JS documentation](https://maplibre.org/maplibre-gl-js/docs/), and the [clustering example](https://maplibre.org/maplibre-gl-js/docs/examples/create-and-style-clusters/).
2. [MapLibre Style Specification](https://maplibre.org/maplibre-style-spec/) and its [expressions](https://maplibre.org/maplibre-style-spec/expressions/).
3. [GeoJSON (RFC 7946)](https://datatracker.ietf.org/doc/html/rfc7946).
4. [OpenFreeMap](https://openfreemap.org/) and its [terms of service](https://openfreemap.org/tos/); the [OpenMapTiles](https://openmaptiles.org/) schema its tiles follow.
5. [OpenStreetMap copyright and license](https://www.openstreetmap.org/copyright): what attribution requires.
6. [Protomaps](https://docs.protomaps.com/): self-hosting a basemap as a single PMTiles file, the alternative if the app should make no third-party requests.
