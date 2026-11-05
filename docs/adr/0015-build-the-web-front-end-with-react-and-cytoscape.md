# 0015. Build the web front end with React, TypeScript, Vite and Cytoscape.js

- **Status:** Accepted
- **Date:** 2026-11-05

## Context

The web front end will be the main way people use Capabilities. It needs an explorable graph view, plus side panels: preset picker, selected and reachable lists, details, search, undo/redo and shareable links. The graph has about 130 things and 42 routes today, with hub nodes (wood, fire) and cycles. It should handle a few thousand nodes later. The reasoner stays in Python ([0013](0013-use-python-for-the-reasoner-cli-and-server.md)).

## Decision

- **Graph rendering: Cytoscape.js**, used directly (not through a React wrapper), with the **dagre** layout (left to right, from primitives to products).
- **UI: React + TypeScript**, built with **Vite**, in a new `web/` directory.
- **Serving:** the FastAPI server serves the built page, so users still run one command (`capabilities serve`). The API moves under `/api`. In development, Vite's dev server forwards `/api` to the Python server.
- **AND/OR drawing:** routes are small junction nodes between a thing and its requirements. Several junctions means "any of these ways". The edges into one junction mean "all of these". This mirrors the data model ([0002](0002-model-capabilities-as-an-and-or-graph.md)).
- **Tests:** Vitest for UI logic, one Playwright smoke test in CI, and pytest for new API endpoints.
- **Dependencies stay minimal**, and each license is checked against the GPL ([0014](0014-license-code-gpl-and-data-cc-by.md)). All of the above are MIT-licensed.

## Consequences

- Contributors who work on the UI need Node in addition to uv. People who only run the tool also need Node to build the page, until we publish built assets or host it.
- Cytoscape's class-based styling maps directly onto statuses (selected, implied, reachable, one step away, out of reach). Its layered layouts suit "what would it take?" trees.
- Cytoscape's state is managed imperatively, outside React. The integration must keep the two in sync: update classes on status changes without recomputing the layout.
- Moving the API under `/api` changes existing URLs. The README is updated in the same change.

## Alternatives considered

- **React Flow.** Best for rich nodes, but it slows past a few hundred nodes and has no layout engine. Could be added later for small focused views.
- **Sigma.js.** Handles very large graphs, but it is weak at layered trees and rich labels, and that scale isn't needed yet.
- **D3.** Full control, but we would build zoom, selection and layout ourselves.
- **A single hand-written HTML file.** No Node needed, but unwieldy once there are panels, history, search and links.
- **ELK layout.** Better layered layouts, but it is EPL-2.0 and needs a license check against the GPL. dagre is the MIT fallback.
- **Svelte or Vue.** Both fine. React has the largest ecosystem and contributor pool.
