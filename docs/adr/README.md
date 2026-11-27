# Architecture Decision Records

Each file records one significant design decision: the context, what we decided, the consequences, and the alternatives we rejected. See [0001](0001-record-architecture-decisions.md) for how this works.

**To add one:** copy [template.md](template.md) to the next number, fill it in, add it to the table below, and include it in the pull request that makes the change. **To change an accepted decision:** write a new ADR that supersedes it, and update only the old one's status line.

| # | Decision | Status |
|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Record design decisions as ADRs | Accepted |
| [0002](0002-model-capabilities-as-an-and-or-graph.md) | Model capabilities as an AND/OR graph with quantity constraints | Accepted |
| [0003](0003-model-timeless-kinds-of-things.md) | Model timeless kinds of things, not history | Accepted; amended by 0036 |
| [0004](0004-store-the-graph-as-yaml-in-git.md) | Store the graph as YAML files in git, validated by JSON Schema | Superseded by 0034 |
| [0005](0005-know-how-never-gates-reachability.md) | Know-how never gates reachability | Accepted |
| [0006](0006-separate-selected-implied-and-reachable.md) | Separate selected, hypothetical, implied and reachable | Accepted; near-miss definition superseded by 0027; free found materials refined by 0032 |
| [0007](0007-compare-ranges-with-three-answers.md) | Compare ranges with three answers; missing data is "maybe" | Accepted |
| [0008](0008-record-the-basis-of-every-number.md) | Record the basis of every number and the status of every reference | Accepted; refined by 0034 |
| [0009](0009-check-feasibility-with-performance-envelopes.md) | Check feasibility with performance envelopes and ballpark bands | Accepted |
| [0010](0010-merge-effect-thresholds-by-the-weakest-shared-bound.md) | Merge effect thresholds by the weakest shared bound | Accepted |
| [0011](0011-routes-can-require-actions-down-to-primitives.md) | Routes can require actions, built down to primitives | Accepted |
| [0012](0012-use-regionality-only-for-warnings.md) | Record regionality; use it only for warnings | Superseded by 0036 |
| [0013](0013-use-python-for-the-reasoner-cli-and-server.md) | Use Python for the reasoner, CLI and local API server | Accepted |
| [0014](0014-license-code-gpl-and-data-cc-by.md) | License the code under GPL-3.0-or-later and the data under CC BY 4.0 | Superseded by 0037 |
| [0015](0015-build-the-web-front-end-with-react-and-cytoscape.md) | Build the web front end with React, TypeScript, Vite and Cytoscape.js | Accepted; drawing and layout superseded by 0023 |
| [0016](0016-recompute-on-every-change.md) | Recompute results on every selection change | Accepted |
| [0017](0017-ui-selection-model.md) | UI selection model: implicit selection, history and shareable state | Accepted; list contents superseded by 0025, their single pane by 0029 |
| [0018](0018-rank-dependencies-by-tech-level.md) | Rank items by tech level | Accepted |
| [0019](0019-desktop-first-mobile-ready.md) | Build desktop-first, without blocking mobile | Accepted |
| [0020](0020-show-a-bounded-number-of-items.md) | Show one level at a time and a bounded number of items | Accepted; graph summaries refined by 0024, replaced by 0030 |
| [0021](0021-colour-for-type-border-for-status-tech-tree-layout.md) | Colour shows type, border shows status; lay the graph out as a tech tree | Accepted; node colouring superseded by 0022, ordering by 0023 |
| [0022](0022-type-strip-with-emoji-on-neutral-nodes.md) | Show type with a coloured strip and emoji on neutral nodes | Accepted |
| [0023](0023-draw-requirements-straight-to-products.md) | Draw requirements straight to products, and order columns by type and name | Accepted |
| [0024](0024-fold-busy-nodes-links-into-summary-nodes.md) | Fold a busy node's extra links into summary nodes | Superseded by 0030 |
| [0025](0025-detail-pane-below-graph-and-chip-lists.md) | Put the detail pane under the graph, and show the side pane as chips | Accepted; status wording superseded by 0028, Could do grouped by 0030 |
| [0026](0026-explain-lines-and-summaries-in-the-detail-pane.md) | Explain lines, summary nodes and know-how in the detail pane | Accepted; summary nodes removed by 0030 |
| [0027](0027-count-one-step-away-as-one-raw-ingredient.md) | Count "one step away" as one raw ingredient, however deep | Accepted |
| [0028](0028-floating-resizable-panes-and-neutral-wording.md) | Float the panes with resizable gaps, and word statuses without assuming a group | Accepted |
| [0029](0029-split-the-side-column-into-two-resizable-panes.md) | Split the side column into two resizable panes | Accepted; keeping a dragged Selected size superseded by 0030 |
| [0030](0030-hide-extra-lines-focus-on-certain-needs-group-actions.md) | Hide busy nodes' extra lines without placeholders, focus on certain needs, and group actions by verb | Accepted |
| [0031](0031-call-categories-classes-and-add-members-in-one-click.md) | Call categories "classes" in the interface, and add their members in one click | Accepted |
| [0032](0032-extract-materials-from-sources-by-routes.md) | Extract materials from sources by ordinary routes | Accepted |
| [0033](0033-build-a-python-data-platform-around-the-graph.md) | Build a Python data platform around the graph | Accepted |
| [0034](0034-build-the-graph-from-upstream-datasets-and-a-curated-layer.md) | Build the graph from upstream datasets and a curated layer | Accepted; "the curated layer always wins" superseded by 0043 |
| [0035](0035-propose-curated-facts-with-audited-agents.md) | Propose curated facts with audited AI agents, reviewed by agents and people | Accepted; models and interfaces, spending caps and the audit log's home superseded by 0048 |
| [0036](0036-place-sources-and-profiles-in-space-and-time.md) | Place sources and profiles in space and time | Accepted |
| [0037](0037-license-the-project-for-non-commercial-use-only.md) | License the project for non-commercial use only | Accepted |
| [0038](0038-serve-the-app-from-a-built-graph-artifact.md) | Serve the app from a built graph artifact (Parquet tables and a manifest, built by dbt) | Accepted |
| [0039](0039-keep-architecture-docs-and-diagrams-current.md) | Keep architecture docs and diagrams current, and teach every technology (LikeC4, docs/architecture) | Accepted |
| [0040](0040-orchestrate-the-build-with-dagster.md) | Orchestrate the build with Dagster, and keep a quick build without it | Accepted |
| [0041](0041-place-sources-with-mrds-deposits-through-a-crosswalk.md) | Place sources with MRDS deposits, matched through a hand-kept crosswalk | Accepted; building without a snapshot superseded by 0044 |
| [0042](0042-show-where-things-are-found-on-a-maplibre-map.md) | Show where things are found on a MapLibre map, over OpenFreeMap tiles | Accepted |
| [0043](0043-take-quantities-from-wikidata-with-upstream-first-and-overrides.md) | Take quantities from Wikidata, upstream first, with overrides | Accepted; keeping curated values that match upstream superseded by 0044 |
| [0044](0044-require-every-upstream-dataset-with-cold-backups-in-git.md) | Require every upstream dataset, with cold backups in git | Accepted |
| [0045](0045-bring-ore-minerals-in-from-upstream-roast-sulphides-and-queue-the-gaps.md) | Bring ore minerals in from upstream, roast copper sulphides, and queue the gaps | Accepted |
| [0046](0046-place-ancient-mines-and-quarries-from-pleiades.md) | Place ancient mines and quarries from Pleiades | Accepted |
| [0047](0047-check-citations-against-openalex-and-crossref.md) | Check citations against OpenAlex and Crossref | Accepted |
| [0048](0048-run-agents-through-claude-code-on-a-claude-subscription.md) | Find sources in code, and ask Claude Code on a Claude subscription only to judge them; start with ore candidates | Accepted |
| [0049](0049-have-agents-quote-sources-for-unverified-routes.md) | Have agents quote sources for routes whose references are all unverified | Accepted |
| [0050](0050-report-withdraw-and-recheck-agent-facts.md) | Report facts as GitHub issues, withdraw agents' facts into a file, and re-check them only when an admin asks | Accepted |
| [0051](0051-write-dates-as-signed-years-and-date-workings-from-periods-and-curated-dates.md) | Write dates as signed years, and date workings from Pleiades' periods and curated dates | Accepted |
| [0052](0052-give-profiles-a-cliopatria-place-and-years-and-find-their-sources-on-the-map.md) | Give profiles a Cliopatria place and years, and find their sources on the map | Accepted |
