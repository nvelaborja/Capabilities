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

### Local server

```bash
uv run capabilities serve                 # http://127.0.0.1:8000
```

Open http://127.0.0.1:8000/docs for interactive API docs where you can try every endpoint in the browser.

| Endpoint | What it does |
|---|---|
| `GET /nodes`, `GET /nodes/{id}` | Browse things, verbs, and routes |
| `GET /profiles`, `GET /jobs` | List presets and example jobs |
| `GET /need/{id}` | Q1: the full tree of what it would take, plus what is certain |
| `POST /explore` | Q2: `{"profile": "...", "select": [], "deselect": [], "hypothetical": []}` |
| `POST /check` | Q3: the same plus `"job": "<id>"` or an inline `"job_spec"` |

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
