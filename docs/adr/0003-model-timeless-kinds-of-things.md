# 0003. Model timeless kinds of things, not history

- **Status:** Accepted
- **Date:** 2026-11-04 (recorded 2026-11-05)

## Context

An early idea was to record who made what, where and when (an attestation layer), alongside individual finds (a specific artifact in a specific museum). Both would greatly increase scope and need careful archaeological sourcing. The core questions are about what physics, chemistry and engineering require, not about chronology. The primary audience is the curious public.

## Decision

We will model what it physically takes to make or do things, timelessly.

- No historical attestation layer: the graph does not say who did what when.
- Nodes are **kinds** of things (granite, copper saw), not individual finds.
- Every node can carry free-form annotations and references, so historical context can be attached without becoming part of the logic.
- Historical groups appear only as **profiles** ([0006](0006-separate-selected-implied-and-reachable.md)): curated starting sets that users can edit.

## Consequences

- The graph stays small enough to curate and to reason over.
- Users bring their own historical claims through profiles and selections, and the tool reasons about what those claims imply.
- Questions like "when was steel first made?" are out of scope.

## Alternatives considered

- **Attestation layer with dates and sites.** Large scope, contested data, and not needed for the three questions.
- **Individual finds as nodes.** Useful for feasibility checks of specific artifacts. Jobs ([0009](0009-check-feasibility-with-performance-envelopes.md)) cover this without adding finds to the graph.
