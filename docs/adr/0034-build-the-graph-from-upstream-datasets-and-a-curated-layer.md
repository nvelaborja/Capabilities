# 0034. Build the graph from upstream datasets and a curated layer

- **Status:** Proposed
- **Date:** 2026-11-20
- **Supersedes (when accepted):** [0004](0004-store-the-graph-as-yaml-in-git.md). Refines [0008](0008-record-the-basis-of-every-number.md): its rules stay for curated facts, and upstream facts carry their dataset and record instead.

## Context

Today every node and route is hand-written YAML, the source of truth ([0004](0004-store-the-graph-as-yaml-in-git.md)). Public datasets already hold most of the **nodes** we need, and far more of them:

- materials and minerals, with properties such as hardness (Wikidata)
- mineral deposits, with coordinates (USGS MRDS)
- ancient places (Pleiades)
- past societies and their technologies (Seshat)
- the literature (OpenAlex, Crossref)

We can't edit most of these datasets, and we don't want to make a habit of editing the ones we could, such as Wikidata.

They hold almost none of the **connective tissue**: the routes that say what it takes to make something, under what conditions. That has to be curated, and it will be most of the curation work.

The "never invent data" rule ([0008](0008-record-the-basis-of-every-number.md)) was never about YAML. It protects the one thing that makes the tool trustworthy: you can trace any answer back to where it came from.

## Decision

We will treat the graph as a **built product**. A pipeline ([0033](0033-build-a-python-data-platform-around-the-graph.md)) builds it from two kinds of input:

1. **Upstream datasets**, snapshotted on each run, with the retrieval date and license recorded. These are the master set for what they cover.
2. **A curated layer** that we write, kept in git and reviewed in pull requests. It does five things:
   - **Adds** what no dataset has: routes, verbs, effects, classes, and things missing upstream.
   - **Maps** our ids to upstream ids (a crosswalk). This is the join key for everything else.
   - **Overrides** an upstream value we believe is wrong, with a reason and a reference.
   - **Suppresses** an upstream record that doesn't belong (a duplicate, bad coordinates, the wrong mineral), with a reason. Suppression is for bad records, not for unwelcome history: a deposit found in modern times stays, with its dates ([0036](0036-place-sources-and-profiles-in-space-and-time.md)).
   - **Annotates** with notes and references.

Rules:

- **Every fact has provenance.** That replaces "every value cites a reference". A fact comes from one of four places:

  | Provenance | What it records | Status rules |
  |---|---|---|
  | **Upstream** | dataset, record id, snapshot date | — |
  | **Curated** | references, with the basis and status rules of [0008](0008-record-the-basis-of-every-number.md) | 0008 |
  | **Override** | what it replaces, why, and its references | 0008 |
  | **Agent-proposed** | the audited run that produced it ([0035](0035-propose-curated-facts-with-audited-agents.md)) | not human-reviewed until a person accepts it |

  Unknown is still fine. Guessing is still not.
- **We never correct upstream sources.** We override locally and say so.
- **Overrides are visible.** Wherever an overridden value appears, the interface says it was overridden, shows the upstream value and source next to ours, and gives the reason.
- **Conflicts between upstream sources become ranges** where the values are numbers (which [0007](0007-compare-ranges-with-three-answers.md) already handles), and otherwise follow a precedence per field. Each field lists its sources in order; the curated layer always wins.
- **Our ids stay our own.** Upstream ids (Wikidata, Pleiades, MRDS) are attributes in the crosswalk, never our primary keys. Ids that people type into URLs shouldn't change when an upstream changes.
- **Gaps become the curation queue.** Upstream nodes with no routes, routes missing citations, unmapped records and overrides awaiting review are all outputs of the build (a mart). The queue is the to-do list for people and agents.
- **The app reads the built graph**, as a versioned build artifact. Whether that is an exported file, Postgres, or Iceberg read directly is decided in a later ADR. The reasoner doesn't care where a fact came from, only what it is.

## Consequences

- The graph grows to whatever the upstream datasets cover. The interface must cope with far more nodes: grouping, filtering, and drawing fewer of them.
- Two places to look: upstream facts in snapshots, curated facts in git. The provenance shown in the app is what keeps that understandable.
- The current YAML becomes the first version of the curated layer. Its JSON Schemas need new fields: upstream ids, overrides, suppressions, provenance.
- A change upstream can change answers. Snapshots make every build reproducible, and comparing two builds shows what changed and why.
- The crosswalk becomes the most important hand-kept table. Errors there spread everywhere, so it gets dbt tests and review.
- `capabilities validate` grows into the pipeline's checks. CI still runs the parts that need no network on the curated layer alone.

## Alternatives considered

- **Keep YAML in git as the only source of truth** ([0004](0004-store-the-graph-as-yaml-in-git.md)). Simple, but copying thousands of upstream records into YAML loses where they came from and goes stale.
- **Make a database the source of truth, edited through an admin screen.** More platform to learn, but no pull-request review of curated facts, which is where mistakes and invented data would get in.
- **Fix errors upstream (edit Wikidata).** It helps others, but it isn't our job, it doesn't work for datasets we can't edit, and it mixes our product with someone else's.
- **Drop suppressed or modern records entirely.** Loses useful context: a deposit that existed but wasn't known to be worked is exactly the kind of "could they have?" the tool is for.
- **Use Wikidata ids as our ids.** Stable and global, but not every curated thing has one, and URLs would stop being readable.
