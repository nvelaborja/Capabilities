# Architecture Decision Records

Each file records one significant design decision: the context, what we decided, the consequences, and the alternatives we rejected. See [0001](0001-record-architecture-decisions.md) for how this works.

**To add one:** copy [template.md](template.md) to the next number, fill it in, add it to the table below, and include it in the pull request that makes the change. **To change an accepted decision:** write a new ADR that supersedes it, and update only the old one's status line.

| # | Decision | Status |
|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Record design decisions as ADRs | Accepted |
| [0002](0002-model-capabilities-as-an-and-or-graph.md) | Model capabilities as an AND/OR graph with quantity constraints | Accepted |
| [0003](0003-model-timeless-kinds-of-things.md) | Model timeless kinds of things, not history | Accepted |
| [0004](0004-store-the-graph-as-yaml-in-git.md) | Store the graph as YAML files in git, validated by JSON Schema | Accepted |
| [0005](0005-know-how-never-gates-reachability.md) | Know-how never gates reachability | Accepted |
| [0006](0006-separate-selected-implied-and-reachable.md) | Separate selected, hypothetical, implied and reachable | Accepted |
| [0007](0007-compare-ranges-with-three-answers.md) | Compare ranges with three answers; missing data is "maybe" | Accepted |
| [0008](0008-record-the-basis-of-every-number.md) | Record the basis of every number and the status of every reference | Accepted |
| [0009](0009-check-feasibility-with-performance-envelopes.md) | Check feasibility with performance envelopes and ballpark bands | Accepted |
| [0010](0010-merge-effect-thresholds-by-the-weakest-shared-bound.md) | Merge effect thresholds by the weakest shared bound | Accepted |
| [0011](0011-routes-can-require-actions-down-to-primitives.md) | Routes can require actions, built down to primitives | Accepted |
| [0012](0012-use-regionality-only-for-warnings.md) | Record regionality; use it only for warnings | Accepted |
| [0013](0013-use-python-for-the-reasoner-cli-and-server.md) | Use Python for the reasoner, CLI and local API server | Accepted |
| [0014](0014-license-code-gpl-and-data-cc-by.md) | License the code under GPL-3.0-or-later and the data under CC BY 4.0 | Accepted |
| [0015](0015-build-the-web-front-end-with-react-and-cytoscape.md) | Build the web front end with React, TypeScript, Vite and Cytoscape.js | Accepted; drawing and layout superseded by 0023 |
| [0016](0016-recompute-on-every-change.md) | Recompute results on every selection change | Accepted |
| [0017](0017-ui-selection-model.md) | UI selection model: implicit selection, history and shareable state | Accepted |
| [0018](0018-rank-dependencies-by-tech-level.md) | Rank items by tech level | Accepted |
| [0019](0019-desktop-first-mobile-ready.md) | Build desktop-first, without blocking mobile | Accepted |
| [0020](0020-show-a-bounded-number-of-items.md) | Show one level at a time and a bounded number of items | Accepted |
| [0021](0021-colour-for-type-border-for-status-tech-tree-layout.md) | Colour shows type, border shows status; lay the graph out as a tech tree | Accepted; node colouring superseded by 0022, ordering by 0023 |
| [0022](0022-type-strip-with-emoji-on-neutral-nodes.md) | Show type with a coloured strip and emoji on neutral nodes | Accepted |
| [0023](0023-draw-requirements-straight-to-products.md) | Draw requirements straight to products, and order columns by type and name | Accepted |
