# Capabilities
A tool to help understand what was possible, and when.

Capabilities is a free knowledge graph of what it physically takes to make things and do things: materials, tools, actions, and conditions like temperature, hardness, and toughness. It answers three questions:

1. **What would it take?** What would it take to produce steel, or cut granite?
2. **What else could they do?** If a group made or did these things, what else was within their reach? What would one more ingredient unlock?
3. **Could it have been done this way?** Could this job have been done with these tools, at this precision, in a plausible time?

The graph is timeless: it models what chemistry, physics, and engineering require, not who did what when. It asks what was *within reach* given the ingredients, not whether anyone actually did it. Historians can use it to reason about specific peoples and periods.

## Quick start

You need [uv](https://docs.astral.sh/uv/) (it installs the right Python for you).

```bash
uv sync                                   # install
uv run capabilities validate              # check every data file
uv run capabilities build                 # build the graph the app and questions read (automatic when needed)
uv run capabilities need steel            # Q1: what would it take to make steel?
uv run capabilities need cut:granite      # Q1 works for actions too
uv run capabilities explore --profile middle-kingdom-egypt                      # Q2
uv run capabilities explore --profile middle-kingdom-egypt --hypothetical hematite  # Q2 what-if
uv run capabilities check granite-slab-saw-cut --profile middle-kingdom-egypt   # Q3
```

The data files in `data/` are the curated layer. `capabilities build` turns them into the built graph in `build/graph/` (Parquet tables and a manifest) with dbt on DuckDB ([ADR 0038](docs/adr/0038-serve-the-app-from-a-built-graph-artifact.md)). The questions and the server read the built graph and rebuild it first whenever the data has changed, so you rarely need to run `build` yourself. The same build runs as [Dagster](docs/architecture/technologies/dagster.md) assets too: `cd pipeline && uv run dg dev` opens a UI at http://localhost:3000 with the lineage from the YAML to the built graph, every dbt test as a check, and a history of runs ([ADR 0040](docs/adr/0040-orchestrate-the-build-with-dagster.md)). Dagster also downloads upstream datasets: "Materialize all" fetches a snapshot of the USGS Mineral Resources Data System, and the build turns its deposits into places where our sources are found (`build/graph/source_occurrences.parquet`, [ADR 0041](docs/adr/0041-place-sources-with-mrds-deposits-through-a-crosswalk.md)). It also asks [Wikidata](https://www.wikidata.org/) for the Mohs hardness of our materials, which the graph then uses over our own values; the detail pane says where each value came from, and shows our earlier value when Wikidata's differs ([ADR 0043](docs/adr/0043-take-quantities-from-wikidata-with-upstream-first-and-overrides.md)). Every dataset is required: the repository keeps a cold backup of each in `snapshots/`, so the graph builds offline and in CI, and a build uses whichever copy is newer, the download or the backup ([ADR 0044](docs/adr/0044-require-every-upstream-dataset-with-cold-backups-in-git.md)). After downloading, `uv run capabilities backup` makes the new download the backup.

Some nodes come from upstream too: ore minerals listed in a hand-kept, referenced crosswalk (`data/crosswalks/ore_minerals.csv`) join the graph from Wikidata and MRDS, each with its deposits on the map and a way to mine it, and copper sulphides are roasted before they are smelted. The build also lists what needs curating next, ore minerals waiting for review first: `uv run capabilities queue` ([ADR 0045](docs/adr/0045-bring-ore-minerals-in-from-upstream-roast-sulphides-and-queue-the-gaps.md)).

Every question command takes `--json` for machine-readable output. `explore` and `check` take `--profile`, `--select`, `--deselect`, and `--hypothetical`. Items are thing ids (`copper-saw`) or actions (`cut:granite`).

### Web app

The web app needs [Node.js](https://nodejs.org/) 22 or later to build, once:

```bash
cd web && npm ci && npm run build && cd ..
uv run capabilities serve                 # then open http://127.0.0.1:8000
```

Pick a preset such as Middle Kingdom Egypt on the right. **Selected** shows your choices. **Implied and reachable** shows what follows: what the selection requires (*implied*), what can be made or done from it, and what is one step away: things that one more raw ingredient, such as an ore, would unlock, however long the chain. Each item is a chip drawn like a graph node. Click any node on the graph, or any chip in a list, to open its details under the graph, reading left to right like the graph: each way to make it with what is met (✓), missing (✗) or unknown (?) and why; what it is and the sources; and what it leads to. Click a requirement to see what *it* needs; the breadcrumb leads back. A class (such as iron ore) stands for any of its members; its details list them, each with an **Add** button. Where things are found is separate from how they are extracted: a ⛰️ **source** (standing trees, the Aswan granite outcrop, a hematite deposit) says where a resource is, and an ordinary route extracts the material, such as felling timber with an edged tool or quarrying granite by pounding. Common sources and hand-gathered materials (standing trees, deadwood, plant fiber, water…) are always available; regional sources (ore deposits, stone outcrops, diamond gravel) must be added or implied. **Expand all dependencies** lists everything it needs at every depth, and **Focus** shows only the node, what it certainly needs and what it directly makes. **Could do** groups actions by verb ("Cut · 15 materials"); click one to list them. Search (press `/`) finds any thing or action, including actions not drawn yet. Undo and redo cover every change, and the address bar always holds a link to the current selection, such as `?preset=middle-kingdom-egypt&add=hematite`.

The graph reads as a technology tree, primitives on the left. A coloured strip with an emoji shows what each node is, and its border shows where it stands. Busy nodes draw lines only to their 8 most advanced neighbours; click one to see all its lines, or use **Expand all**. Click any line to see why it is there: the routes behind it, the role and threshold of what it joins, and what its style and label mean. **Legend** in the graph toolbar explains the strips and borders. Drag the gaps between panes (or focus one and use the arrow keys) to resize them; double-click a gap to reset. Selected fits its chips up to half the column, again after every change to the selection, and Implied and reachable takes the rest. Pick Auto, Light or Dark in the header.

**Where it's found**, in the details of a source or of a material extracted from one (hematite, malachite, granite…), swaps the graph for a map of every known place, from the USGS Mineral Resources Data System. A filled dot was worked by a known year, and a ring is present with no known working date. Groups of nearby places show a count; select one to zoom in, and select a place for its details and a link to its record ([ADR 0042](docs/adr/0042-show-where-things-are-found-on-a-maplibre-map.md)). The map needs an MRDS snapshot (see above) and fetches its background tiles from [OpenFreeMap](https://openfreemap.org/) when it opens.

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
| `GET /api/graph` | Every drawable node and edge, with tech levels, plus every possible action for search and what each node certainly needs (for focus mode). Add `?action=cut:limestone` to draw extra actions |
| `GET /api/need/{id}` | Q1: the full tree of what it would take, plus what is certain |
| `POST /api/explore` | Q2: `{"profile": "...", "select": [], "deselect": [], "hypothetical": []}`. Includes a status for every node and what implies each implied item |
| `POST /api/explain` | What a node needs, one level deep, each requirement met / missing / unknown with a reason: the same body plus `"node": "<id>"`. Also what the node is (description, numbers, sources), each route's references, and what it leads to. Add `"all": true` for every certain need at every depth. Know-how ids work too |
| `POST /api/explain-edge` | Why a line joins two nodes: the same body plus `"source"` and `"target"`. Each route behind it, the source's role and threshold, met or not and why; or the "is a" link |
| `POST /api/check` | Q3: the same body plus `"job": "<id>"` or an inline `"job_spec"` |
| `GET /api/occurrences/{id}` | Where a material or source is found: each source it comes from, with how many places are mapped and how many were worked, the datasets, and every place as GeoJSON points |

### Tests

```bash
uv run pytest                             # every package's tests; builds the graph once into a temporary directory
```

## Layout

```
schema/            JSON Schemas for every data file type
data/              the graph: quantities, things, verbs, routes, profiles; crosswalks to upstream datasets, overrides and suppressions
snapshots/         cold backups of the upstream datasets, under their own licenses
examples/          example jobs and worked results
packages/core/     the graph, reasoner, validator and CLI (`capabilities`), with its tests
packages/api/      the local API server, which also hosts the web app
pipeline/          builds the graph: loading, the dbt project (pipeline/dbt), the Dagster assets, and their tests
web/               the web app (React, TypeScript, Cytoscape.js)
build/             upstream snapshots, the built graph and the DuckDB warehouse (generated, not in git)
docs/              architecture and technology guides (docs/architecture/), data format, and design decisions (docs/adr/)
```

- Architecture, the data pipeline, and a guide to every technology we use: [docs/architecture/](docs/architecture/README.md). With the app running, the diagrams are at http://127.0.0.1:8000/architecture/
- Data format and reasoning rules: [docs/data-format.md](docs/data-format.md)
- Worked examples of the three questions: [examples/README.md](examples/README.md)
- Design decisions and why we made them: [docs/adr/](docs/adr/README.md)

## Contributing data

Every route must cite at least one source, and every number should say how it was obtained (measured, derived, estimated, or unknown). Unknown is fine; guessing is not. Search the data for `TODO-source` to find claims that still need sources, and run `uv run capabilities validate` before opening a pull request. If you add or change a citation, run `uv run capabilities credits` to update [CREDITS.md](CREDITS.md). Contributions are accepted under the project's licenses.

## License

Capabilities is free to use, study, change and share for any **non-commercial** purpose: personal use, research, teaching, and use by charities, schools, public bodies and similar organizations. Commercial use is not allowed. Because of that, it is source-available rather than "open source" in the strict sense ([ADR 0037](docs/adr/0037-license-the-project-for-non-commercial-use-only.md)).

- **Code** (everything outside `data/`): [PolyForm Noncommercial License 1.0.0](LICENSE).
- **Data** (`data/`, and any graph built from it): [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)](data/LICENSE). You can reuse and adapt it for non-commercial work, including research and publications, as long as you credit the Capabilities project and share adaptations under the same license.

[CREDITS.md](CREDITS.md) lists the datasets, published works, software and design research the project builds on, with their licenses.
