# Architecture

How Capabilities is built, why, and how each technology in it works. These docs grow with the project: every pull request that changes the architecture, the data flow or the technology updates them ([ADR 0039](../adr/0039-keep-architecture-docs-and-diagrams-current.md)).

## Start here

| Document | What it covers |
|---|---|
| [Overview](overview.md) | The parts of the system, how a question travels from the browser to the reasoner and back, and the main design decisions. Start here. |
| [Data pipeline](data-pipeline.md) | Reference for the build: every input, stage, table, output, check and command. |
| [Technologies](technologies/README.md) | One page per technology: what it is, how it works, what we use it for, where it lives in the repository, and what to read next. |
| [Diagrams](diagrams/) | The LikeC4 model behind the diagrams below. |

## Diagrams

The diagrams are written as code in [LikeC4](technologies/likec4.md) (`diagrams/*.c4`) and built into a small website.

- **Served by the app:** after `cd web && npm run build`, run `uv run capabilities serve` and open <http://127.0.0.1:8000/architecture/>.
- **Live preview while editing:** `cd web && npm run diagrams` opens a preview that redraws as you edit the `.c4` files.
- **Check:** `cd web && npm run diagrams:check` validates the model. CI checks it on every pull request as part of the web build.

| View | Shows |
|---|---|
| `index`: Capabilities, the whole project | The master diagram: people, outside systems, every part of the system, and how data flows between them. |
| `pipeline`: The data pipeline | How `capabilities build` turns the curated YAML into the built graph the app reads. |

## Keeping this current

When a pull request changes how the system is built:

1. Update the LikeC4 model (`diagrams/model.c4`) and the views it affects. New parts go into the `index` view.
2. Update the [overview](overview.md) and, if the data flow changes, the [data pipeline](data-pipeline.md) reference.
3. If it introduces a technology, add a page under [technologies/](technologies/README.md) that teaches it, using the same sections as the existing pages.
