# 0035. Propose curated facts with audited AI agents, reviewed by agents and people

- **Status:** Proposed
- **Date:** 2026-11-20

## Context

Upstream datasets give us nodes. Routes, citations and crosswalk entries have to be curated ([0034](0034-build-the-graph-from-upstream-datasets-and-a-curated-layer.md)), and the curation queue will be far longer than one person can work through by hand. AI agents can research and draft routes, find and check references, and challenge each other's work. They can also produce confident, plausible, invented facts and citations, which is exactly what [0008](0008-record-the-basis-of-every-number.md) forbids.

If something turns out wrong later, we need to find every fact that came from the same run, prompt or model, and see how it was reviewed.

## Decision

We will run AI agents as a stage of the pipeline: they propose curated facts, other agents challenge them, people decide, and every step is logged.

**Flow, per item in the curation queue:**

1. **Propose.** A proposer agent drafts the missing piece, such as a route for an upstream material that has none. It searches and reads sources with web search and fetch tools, and returns structured output that matches the curated layer's schema. Every claim must cite a source it actually retrieved, with the quoted passage that supports it.
2. **Check mechanically.** Code, not a model, then verifies:
   - each cited URL resolves;
   - the quoted passage appears in the retrieved text;
   - books and papers match a real work in OpenAlex or Crossref;
   - every id exists;
   - the proposal passes the schemas and `validate`.

   A proposal that fails is rejected or sent back, never fixed silently.
3. **Challenge.** A reviewer agent receives the proposal and its sources, but not the proposer's reasoning. It is instructed to find what is wrong: unsupported claims, overreach beyond what a source says, missing requirements, implausible conditions. It returns a verdict (accept, revise, reject) with objections, each tied to a claim. Revisions loop back to the proposer, a bounded number of times.
4. **Decide.** Proposals the agents accept go into a pull request against the curated layer, grouped and labelled as agent-proposed. A person merges, edits or rejects them. Merging is the human acceptance.

**Status and display:**

- Agent-proposed facts carry provenance `agent-proposed` until a person accepts them. Their references stay `unverified` until someone reads the source ([0008](0008-record-the-basis-of-every-number.md)). Passing the agents' review is not verification.
- The interface labels agent-proposed facts everywhere they appear.
- We still have to decide whether unreviewed proposals take part in reasoning:
  - not at all;
  - with a switch;
  - as "maybe", so that a route supported only by an agent can never make something a firm yes ([0007](0007-compare-ranges-with-three-answers.md)).

**Audit log.** Every run appends records to an audit table in the lakehouse, which is never updated in place:

- the queue item;
- the prompt version (prompts live in git);
- the model id and settings;
- every tool call, including the URLs searched and fetched;
- the raw output;
- the result of each mechanical check;
- each reviewer verdict and its objections;
- the pull request, and the human decision.

Each curated fact links back to the run that produced it. From any fact we can find its run, and from any run, prompt version or model, every fact it produced.

**Models and interfaces (initial choice, revisit by measurement):**

- The pipeline drives the loop. Each step is a Dagster asset calling the Claude API: the proposer uses the server-side web search and fetch tools and structured outputs; the reviewer gets the fetched sources as documents. The orchestration and audit records stay in our pipeline, where the data platform work is.
- Start with Claude Opus 5.5 for both roles. Measure on a hand-labelled set of known-good and known-bad routes before trying a different reviewer model or effort level. A reviewer that disagrees with the proposer for the right reasons matters more than which model it is.
- Large batches that aren't urgent can use the Message Batches API, at lower cost.
- Hosted agents (Claude Managed Agents) are the alternative if the research loop outgrows a pipeline step.

## Consequences

- The curation queue can be worked systematically, with people spending their time on decisions rather than drafting.
- Costs money per item. Runs need budgets and a way to stop, and the queue needs priorities (for example, items that unlock the most).
- Agents will still get things wrong in ways the checks don't catch: a real source quoted out of context, a plausible but false condition. The human gate and the "unverified" status exist for this.
- The audit log is a dataset of its own, and a good one for evaluating prompt and model changes over time.
- Prompts become versioned code with their own tests (the hand-labelled set).
- Agent output must never land in the curated layer without a pull request.

## Alternatives considered

- **Hand curation only.** Trustworthy, but it can't keep up with the upstream nodes.
- **Agents write directly into the graph.** Fast, and invented facts would go straight to users.
- **One agent that drafts and reviews its own work.** Cheaper, but self-review tends to agree with itself. An independent reviewer without the proposer's reasoning catches more.
- **Ask the model for references from memory.** That is how invented citations happen. References must come from sources retrieved during the run, checked by code.
