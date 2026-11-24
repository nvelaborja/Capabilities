# 0042. Show where things are found on a MapLibre map, over OpenFreeMap tiles

- **Status:** Accepted
- **Date:** 2026-11-22

## Context

[0036](0036-place-sources-and-profiles-in-space-and-time.md) asks for a map view: choosing a material shows every place it can be found, across every source it is extracted from. Each place is marked as worked (with its dates) or present but not known to be worked. A material found almost everywhere says so instead of drawing thousands of points. It named MapLibre GL (BSD-3-Clause) for the map.

[0041](0041-place-sources-with-mrds-deposits-through-a-crosswalk.md) gives us those places: `source_occurrences.parquet`, 14,488 points from MRDS. One material can have nearly 5,000 of them (malachite). The web app is React with Cytoscape for the graph ([0015](0015-build-the-web-front-end-with-react-and-cytoscape.md)). Status must never rely on colour alone, and nothing may be available only on hover ([0019](0019-desktop-first-mobile-ready.md)).

A map needs a basemap: land, borders and place names drawn from tiles. Tiles either come from a server or are hosted by us.

## Decision

**The API.**
- `GET /api/occurrences/{id}` takes a material or a source.
- A material is found at the places of every source that routes extract it from (`Graph.sources_of`); a source at its own places. Anything else is a 404.
- The answer lists:
  - each source, with its availability, its curated regions, how many places are mapped and how many are known to have been worked;
  - the upstream datasets, with when they were retrieved;
  - every place, as a GeoJSON `FeatureCollection` of points carrying what the popup needs.
- The server loads the occurrences once, at start-up, beside the graph (`load_occurrences` in `capabilities.built`, shaped by `capabilities.places`). The app reads the longitude and latitude columns, so it needs no spatial extension.
- Responses over 1 KB are gzip-compressed. Malachite's 2.1 MB of GeoJSON becomes 160 KB.

**The web app.**
- A material taken from a source, or a source itself, gets a **Where it's found** button in its detail pane.
- The map then replaces the graph in the main area, and **Back to the graph** returns. The detail and side panes stay as they are.
- MapLibre GL JS is loaded only when the map first opens. It is a separate 1 MB chunk, and its web worker is bundled as its own file, given to MapLibre with `setWorkerUrl`.
- Places are clustered, and each cluster shows its count; selecting a cluster zooms in.
- A single place is a **filled dot** when it is known to have been worked by a year, and a **ring** when it is present with no known working date. The shape carries the difference, the panel's key explains it, and the popup says it in words.
- Selecting a place opens a popup, on click or tap and never on hover. It shows the place's name, where it is, its state in words, MRDS's development status and deposit type, and a link to its record in the dataset it came from. Upstream text is set as text, never as HTML, and a link is followed only if it is http or https.
- Places at the same coordinates never separate, however far you zoom (in MRDS, up to 10 deposits share one point). The popup therefore lists every place under the pointer ("7 places here").
- A panel on the map gives one line per source:
  - its counts;
  - "found almost everywhere, so not mapped" for a ubiquitous source;
  - or "no mapped places yet", with the curated regions, for an unmapped one.

  It also says where the data came from and that it is modern, and explains an empty map: a made material, or no snapshot downloaded.
- Colours come from `theme.css`, as the graph's do. The map uses the source type's colours, in both themes.

**The basemap: OpenFreeMap.**
- [OpenFreeMap](https://openfreemap.org/)'s public vector tiles of OpenStreetMap data: `positron` in the light theme and `dark` in the dark one.
- It needs no key or account, sets no cookies, has no view limits, and allows any use. MapLibre shows the required attribution (OpenFreeMap, OpenMapTiles, OpenStreetMap) automatically.
- The browser fetches the tiles from OpenFreeMap. That is the app's first request to a third party, and it happens only when someone opens the map.

## Consequences

- The M1 requirement "selecting hematite shows its deposits on the map" is met: 2,655 places, 659 of them known to have been worked.
- The background map needs network access to OpenFreeMap. If its style can't be loaded, the map switches to a plain background in the theme's colour, draws the places on it without cluster counts (text needs the basemap's fonts), and says the background map couldn't be loaded. The panel still gives the counts.
- OpenFreeMap sees the IP address and map area of anyone who opens the map, as any tile server would. If the app is hosted for others, the README or an about page should say so, or we self-host the tiles (below).
- The web bundle grows by about 1 MB of JavaScript and 520 KB of worker, but only for people who open the map.
- Profile areas, polity borders and a time control (M4) go on this same map. The occurrence states are already in place for "worked by the profile's date".
- Screenshots of the map need an animating, visible browser: MapLibre draws on animation frames. Tests therefore cover the data and text (`places.ts`), not the canvas.

## Alternatives considered

- **Self-hosted tiles (Protomaps PMTiles, or OpenFreeMap's own server).** There are no third-party requests, and the map works offline. But a detailed world basemap is on the order of a hundred gigabytes (much less if cut to low zooms) to download, store and serve. That is worth revisiting with the lakehouse and Kubernetes (M5–M6), when there is storage to put it in.
- **A bundled Natural Earth outline (public domain, under a megabyte of GeoJSON at small scale).** It works offline with no third party, but it has no place names and little to orient by. It would be our fallback if OpenFreeMap disappeared.
- **Commercial tiles (MapTiler, Mapbox, Stadia).** Polished, but they need an API key and an account, and limit or charge for use.
- **Leaflet with raster tiles.** Lighter and familiar, but OpenStreetMap's own tile servers restrict heavy use in their usage policy. MapLibre's vector tiles style themselves for light and dark, and MapLibre is what ADR 0036 chose.
- **The map in a dialog, or a separate page.** A dialog is cramped for a world map. A separate page would lose the detail pane and the selection beside it.
- **Every place as a separate marker element.** Thousands of DOM nodes are slow, and they don't cluster. Drawing on WebGL layers scales to every MRDS deposit.
