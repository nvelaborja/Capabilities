# Capabilities
A tool to help understand what was possible, and when.

Capabilities is an open knowledge graph of what it physically takes to make things and do things: materials, tools, actions, and conditions like temperature, hardness, and toughness. It answers three questions:

1. **What would it take?** What would it take to produce steel, or cut granite?
2. **What else could they do?** If a group made or did these things, what else was within their reach? What would one more ingredient unlock?
3. **Could it have been done this way?** Could this job have been done with these tools, at this precision, in a plausible time?

The graph is timeless: it models what chemistry, physics, and engineering require, not who did what when. It asks what was *within reach* given the ingredients, not whether anyone actually did it. Historians can use it to reason about specific peoples and periods.

## Quick start

You need [uv](https://docs.astral.sh/uv/) (it installs the right Python for you).

```bash
uv sync                                   # install
uv run capabilities validate              # check every data file
uv run capabilities need steel            # Q1: what would it take to make steel?
uv run capabilities need cut:granite      # Q1 works for actions too
uv run capabilities explore --profile middle-kingdom-egypt                      # Q2
uv run capabilities explore --profile middle-kingdom-egypt --hypothetical hematite  # Q2 what-if
uv run capabilities check granite-slab-saw-cut --profile middle-kingdom-egypt   # Q3
```

Every command takes `--json` for machine-readable output. `explore` and `check` take `--profile`, `--select`, `--deselect`, and `--hypothetical`. Items are thing ids (`copper-saw`) or actions (`cut:granite`).

### Web app

The web app needs [Node.js](https://nodejs.org/) 22 or later to build, once:

```bash
cd web && npm ci && npm run build && cd ..
uv run capabilities serve                 # then open http://127.0.0.1:8000
```

Pick a preset such as Middle Kingdom Egypt on the right. **Selected** shows your choices. **Implied and reachable** shows what follows: what they must have had (*implied*), what they could have made or done, and what is one step away. Each item is a chip drawn like a graph node. Click any node on the graph, or any chip in a list, to open its details under the graph, reading left to right like the graph: each way to make it with what is met (✓), missing (✗) or unknown (?) and why; what it is and the sources; and what it leads to. Click a requirement to see what *it* needs; the breadcrumb leads back. **Expand all dependencies** lists everything it needs at every depth, and **Focus** shows only that part of the graph. Search (press `/`) finds any thing or action, including actions not drawn yet. Undo and redo cover every change, and the address bar always holds a link to the current selection, such as `?preset=middle-kingdom-egypt&add=hematite`.

The graph reads as a technology tree, primitives on the left. A coloured strip with an emoji shows what each node is, and its border shows where it stands. Busy nodes show their 8 most advanced links; the rest fold into a dashed “Heat → 4 more materials” node, which you can click to see and unfold, or use **Expand all**. Click any line to see why it is there: the routes behind it, the role and threshold of what it joins, and what its style and label mean. **Legend** in the graph toolbar explains the strips and borders. Pick Auto, Light or Dark in the header.

To work on the web app with live reload, run the API and the Vite dev server side by side:

```bash
uv run capabilities serve                 # API on :8000
cd web && npm run dev                     # app on http://localhost:5173, forwarding /api to :8000
```

`npm test`, `npm run lint` and `npm run typecheck` check the web code. See [web/](web/) and [ADR 0015](docs/adr/0015-build-the-web-front-end-with-react-and-cytoscape.md).

### Local server

```bash
uv run capabilities serve                 # http://127.0.0.1:8000
```

The server hosts the web app at `/` (if built), the API under `/api`, and interactive API docs at http://127.0.0.1:8000/docs, where you can try every endpoint in the browser.

| Endpoint | What it does |
|---|---|
| `GET /api/nodes`, `GET /api/nodes/{id}` | Browse things, verbs, and routes |
| `GET /api/profiles`, `GET /api/jobs` | List presets and example jobs |
| `GET /api/graph` | Every drawable node and edge, with tech levels, plus every possible action for search. Add `?action=cut:limestone` to draw extra actions |
| `GET /api/need/{id}` | Q1: the full tree of what it would take, plus what is certain |
| `POST /api/explore` | Q2: `{"profile": "...", "select": [], "deselect": [], "hypothetical": []}`. Includes a status for every node and what implies each implied item |
| `POST /api/explain` | What a node needs, one level deep, each requirement met / missing / unknown with a reason: the same body plus `"node": "<id>"`. Also what the node is (description, numbers, sources), each route's references, and what it leads to. Add `"all": true` for every certain need at every depth. Know-how ids work too |
| `POST /api/explain-edge` | Why a line joins two nodes: the same body plus `"source"` and `"target"`. Each route behind it, the source's role and threshold, met or not and why; or the "is a" link |
| `POST /api/check` | Q3: the same body plus `"job": "<id>"` or an inline `"job_spec"` |

### Tests

```bash
uv run pytest
```

## Layout

```
schema/            JSON Schemas for every data file type
data/              the graph: quantities, things, verbs, routes, profiles
examples/          example jobs and worked results
src/capabilities/  reasoner, CLI, and API server
web/               the web app (React, TypeScript, Cytoscape.js)
tests/             pytest suite
docs/              data format, reasoning rules, and design decisions (docs/adr/)
```

- Data format and reasoning rules: [docs/data-format.md](docs/data-format.md)
- Worked examples of the three questions: [examples/README.md](examples/README.md)
- Design decisions and why we made them: [docs/adr/](docs/adr/README.md)

## Contributing data

Every route must cite at least one source, and every number should say how it was obtained (measured, derived, estimated, or unknown). Unknown is fine; guessing is not. Search the data for `TODO-source` to find claims that still need sources, and run `uv run capabilities validate` before opening a pull request.

## License

- **Code** (everything outside `data/`): [GNU GPL v3.0 or later](LICENSE).
- **Data** (`data/`): [Creative Commons Attribution 4.0 International (CC BY 4.0)](data/LICENSE). You can reuse and adapt it for any purpose, including in research and publications, as long as you credit the Capabilities project.
