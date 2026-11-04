# Capabilities
A tool to help understand what was possible, and when.

Capabilities is an open knowledge graph of what it physically takes to make things and do things: materials, tools, know-how, and conditions like temperature and hardness. It is built to answer three questions:

1. **What would it take?** What would it take to produce steel, or cut granite?
2. **What else could they do?** If a group could do X, what else was within their reach? What would one more technique unlock?
3. **Could it have been done this way?** Could this job have been done with these tools, at this precision, in a plausible time?

The graph is timeless: it models what chemistry, physics, and engineering require, not who did what when. Historians can use it to reason about specific peoples and periods.

## Status

Early design. The repo contains the data format (JSON Schemas), a hand-built seed slice of about 80 nodes and 38 routes, and worked examples. There is no reasoner or website yet.

- Data format and reasoning rules: [docs/data-format.md](docs/data-format.md)
- Worked examples of the three questions: [examples/README.md](examples/README.md)

## Layout

```
schema/      JSON Schemas for every file type
data/        the graph: quantities, things, verbs, routes, profiles
examples/    example jobs and worked results
docs/        format and design notes
```

## Contributing data

Every route must cite at least one source, and every number should say how it was obtained (measured, derived, estimated, or unknown). Unknown is fine; guessing is not. Search the data for `TODO-source` to find claims that still need sources.
