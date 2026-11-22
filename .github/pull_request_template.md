## What this does



## Architecture docs ([ADR 0039](https://github.com/nvelaborja/Capabilities/blob/main/docs/adr/0039-keep-architecture-docs-and-diagrams-current.md))

- [ ] The LikeC4 model and affected views in `docs/architecture/diagrams/` are updated (new parts are in the `index` view)
- [ ] `docs/architecture/overview.md` is updated, and `data-pipeline.md` if the data flow changed
- [ ] A new technology has a page in `docs/architecture/technologies/` that teaches it
- [ ] None of the above apply: this PR doesn't change the architecture, the data flow or the technology

## Checks

- [ ] `uv run capabilities validate` and `uv run pytest` pass
- [ ] Web changes: `npm run lint && npm run typecheck && npm test && npm run build` pass in `web/`
- [ ] New data or citations: `uv run capabilities credits` has updated `CREDITS.md`; new dependencies or datasets are licensed compatibly ([ADR 0037](https://github.com/nvelaborja/Capabilities/blob/main/docs/adr/0037-license-the-project-for-non-commercial-use-only.md))
