# LikeC4

## What it is

LikeC4 is a language and toolset for architecture diagrams as code. You describe your system once, as a *model* in `.c4` text files: its people, systems, containers and how they relate. You then declare *views*, each showing a chosen part of the model. LikeC4 lays the diagrams out automatically and builds them into an interactive website. Because the model is text, diagrams are reviewed in pull requests like code, and every view stays consistent with the one model.

## How it works

**The C4 model.** LikeC4 is based on Simon Brown's C4 model, which describes software at four zoom levels:

1. **Context**: the system and the people and systems around it.
2. **Containers**: the separately running or deployable parts, such as an app, a database or a service.
3. **Components**: the parts inside a container.
4. **Code.**

Diagrams at each level answer different questions for different readers.

**Specification.** In `specification { }` you define your own element kinds (`actor`, `container`, `store`...), their default shapes and colours, and tags. LikeC4 doesn't force C4's vocabulary on you.

**Model.** In `model { }` you declare elements, nested inside each other (`capabilities = system { core = container { ... } }`), each with a title, description and technology. You declare relationships with `->` and a label: `capabilities.web -> capabilities.api 'calls /api'`. Elements are referred to by their path, such as `capabilities.core.built`.

**Views.** In `views { }` each `view` selects what to show with predicates: `include *` (the top level and its relationships), `include capabilities.*` (an element's children), `exclude ...`, and styles that apply only to that view. Relationships between included elements are drawn automatically. `autoLayout LeftRight` changes the layout direction. The view named `index` is the default view.

**Tools.** The `likec4` command validates the model, starts a live preview, builds a static website, and exports images. Editor extensions add highlighting and live previews.

## How we use it

| View | Purpose |
|---|---|
| `index` | The master diagram of the whole project. Everything that exists goes here. |
| `pipeline` | The data pipeline, from the curated layer to the built graph. |

`npm run build` in `web/` builds the diagrams into `web/dist/architecture` (with base `/architecture/` and hash-based links, so any view can be reloaded or shared). The API server hosts them at `/architecture/`.

Every pull request that changes the architecture updates the model and the views it affects ([ADR 0039](../../adr/0039-keep-architecture-docs-and-diagrams-current.md)).

## Where it lives

| What | Where |
|---|---|
| Element kinds and tags | `docs/architecture/diagrams/specification.c4` |
| The model | `docs/architecture/diagrams/model.c4` |
| The views | `docs/architecture/diagrams/views.c4` |
| The `likec4` tool | A dev dependency of `web/` (`web/package.json`) |

```bash
cd web
npm run diagrams          # live preview while editing the .c4 files
npm run diagrams:check    # validate the model
npm run diagrams:build    # build into web/dist/architecture (npm run build does this too)
```

## Things to know

- Tags (`#generated`) must come first inside an element's braces.
- Model what exists. Planned parts join the model in the pull request that builds them, so the diagrams never describe a system that isn't there.
- Prefer one relationship with a clear label over several vague ones; the label is what readers see on the line.
- LikeC4 is MIT-licensed and only used at build time.

## Further reading

1. [The C4 model](https://c4model.com/): the ideas behind it, in a few pages.
2. [LikeC4](https://likec4.dev/): start with the [DSL introduction](https://likec4.dev/dsl/intro/).
3. [Specification](https://likec4.dev/dsl/specification/), [model](https://likec4.dev/dsl/model/) and [views](https://likec4.dev/dsl/views/) in detail.
4. [The CLI](https://likec4.dev/tooling/cli/) and [deploying a static website](https://likec4.dev/guides/static-website/).
5. [LikeC4 on GitHub](https://github.com/likec4/likec4).
