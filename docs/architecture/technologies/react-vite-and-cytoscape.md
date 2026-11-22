# React, Vite and Cytoscape.js

## What it is

The web app is written in **TypeScript** (JavaScript with types), using **React** to build the interface from components, **Vite** to run it during development and bundle it for production, and **Cytoscape.js** to draw and lay out the graph.

## How it works

**React.** The interface is a tree of *components*, functions that return what should be on screen for the current data. When data changes (*state*), React calls the affected components again and updates only the parts of the page that changed. *Hooks* such as `useState` and `useEffect` give components state and side effects; our own hooks (`useExplore`, `useExplain`, `usePaneSizes`) wrap fetching and layout logic.

**TypeScript.** Types catch mistakes before the code runs. `web/src/api/types.ts` mirrors the API's JSON shapes, so a change on one side shows up as a type error on the other.

**Vite.** In development, `npm run dev` serves the source files almost unchanged, reloads modules in place as you edit, and forwards `/api` to the Python server. For production, `npm run build` type-checks with `tsc` and bundles everything into a few optimized files in `web/dist`, which the API server hosts.

**Cytoscape.js.** A graph library: you give it nodes and edges as data, and a stylesheet that maps data to visual properties (colours, shapes, labels). It handles drawing on a canvas, zooming, panning and selection. We compute our own *tech-tree* layout, with columns by tech level, and give Cytoscape the positions.

## How we use it

The app shows the graph as a technology tree, the selection and what follows from it in side panes, and details for any node or line in a pane under the graph ([ADRs 0015 to 0031](../../adr/README.md) record the design). Colours come from CSS custom properties in `web/src/theme.css`, for light and dark themes. The graph's stylesheet reads them too, so no colour is hard-coded.

## Where it lives

| What | Where |
|---|---|
| Typed API client | `web/src/api/` |
| Graph drawing, layout, focus mode, folding | `web/src/graph/` |
| Detail pane | `web/src/detail/` |
| Side panes, chips, search, layout | `web/src/panes/`, `web/src/chips/`, `web/src/search/`, `web/src/layout/` |
| State: selection history, links, theme | `web/src/state/` |
| Tests (Vitest) | beside the code, `*.test.ts(x)` |

```bash
cd web
npm ci            # install exactly as locked
npm run dev       # http://localhost:5173, forwarding /api to `capabilities serve` on :8000
npm test          # Vitest
npm run lint && npm run typecheck
npm run build     # web/dist, plus the architecture diagrams in web/dist/architecture
```

## Things to know

- Status must never rely on colour alone, and nothing may be available only on hover ([ADR 0019](../../adr/0019-desktop-first-mobile-ready.md), [ADR 0022](../../adr/0022-type-strip-with-emoji-on-neutral-nodes.md)).
- Never hard-code colours in `graph/styles.ts`; add a token to `theme.css`.
- The web app is TypeScript, not Python, because the browser runs JavaScript ([ADR 0033](../../adr/0033-build-a-python-data-platform-around-the-graph.md)).

## Further reading

1. [Learn React](https://react.dev/learn): the official tutorial, especially "Thinking in React" and "Managing State".
2. [TypeScript documentation](https://www.typescriptlang.org/docs/): "TypeScript for JavaScript Programmers" is a quick start.
3. [Vite guide](https://vite.dev/guide/).
4. [Cytoscape.js](https://js.cytoscape.org/): elements, the stylesheet, and layouts.
