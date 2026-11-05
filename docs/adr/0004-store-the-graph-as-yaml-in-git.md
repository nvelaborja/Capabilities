# 0004. Store the graph as YAML files in git, validated by JSON Schema

- **Status:** Accepted
- **Date:** 2026-11-04 (recorded 2026-11-05)

## Context

The data has to be open, reviewable and citable, and contributions should go through review. The graph is small (around 100–200 nodes) and will stay small for a while.

## Decision

We will store the graph as one YAML file per node under `data/`, validated by JSON Schemas (Draft 2020-12) in `schema/`. Ids are unique across all node types, and file names match ids. `capabilities validate` checks schemas, references between nodes, and evidence gaps.

## Consequences

- Every change is a reviewable diff, with history and blame for free.
- Contributors need no database or account, only a text editor and a pull request.
- The schemas are language-neutral, so other tools can read the data.
- Queries load the whole graph into memory. That is fine at this size. A database (local first) is a later step once scale demands it, and these files stay the source of truth until we decide otherwise in a new ADR.

## Alternatives considered

- **Graph database (Neo4j) from the start.** Powerful queries, but harder to review, harder to contribute to, and not needed at this size.
- **Wikibase.** Good for crowdsourcing, but it doesn't model our AND/OR routes or quantity conditions naturally.
- **JSON instead of YAML.** Easier to parse, but harder for people to write and review.
