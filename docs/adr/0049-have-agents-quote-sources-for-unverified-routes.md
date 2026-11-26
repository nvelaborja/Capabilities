# 0049. Have agents quote sources for routes whose references are all unverified

- **Status:** Proposed
- **Date:** 2026-11-25

## Context

[0048](0048-run-agents-through-claude-code-on-a-claude-subscription.md) built the agent pipeline on ore candidates: code finds the sources and passages, a proposer on Claude Code only chooses one, code checks it, a reviewer challenges it, and a person merges a draft pull request. It used about 0.3–0.4 points of a Pro plan's five-hour window per item, and accepted nothing wrong in three evaluations and one real run.

The curation queue's next agent task is `route_unverified`: a route none of whose references is `verified` or `secondary`. On 2026-11-25 the queue held 51; 40 are curated routes, and 11 are the mining routes copied for each ore mineral, which take their template's references. The routes cite 70 references, 50 of them unverified and none with a quote; only 9 of the 40 routes have a reference with a URL or a DOI. Most cite books (Craddock 1995, Tylecote 1992, Rothenberg 1972) that can't be quoted from the web.

Only a person who read a work marks its reference `verified` ([0035](0035-propose-curated-facts-with-audited-agents.md), [0047](0047-check-citations-against-openalex-and-crossref.md)), so agents can't take a route off the queue. They can shorten a person's work: "read a book" becomes "check this sentence on this page".

0048's code assumed ore candidates in places: the run, the curator, the gate and the pull request named the crosswalk, its rows and minerals.

## Decision

**Agent runs take a task.** The run, curator, usage thresholds, library of sources, audit log, gate and pull request are shared; a task (`agents/task.py`) supplies its items, what a passage must say, its prompts, what a proposal is, its checks, the change it makes and the files it writes. Ore candidates are the first task (`ore_candidates`, 0048), and route sources the second (`route_sources`). The Dagster job's op is `curate`, with `task` and `names` (the items to run, instead of the top of the queue) in its config.

**A route source proposal is one of two changes to the route's file:**

1. **A quote for a reference the route already cites**, when the work's own page has a sentence supporting what the reference says it supports: its URL, or, for a work OpenAlex matched with certainty (`found`, never `possible` or a review of it), the free copy OpenAlex lists. The quote and `proposed_by` are added to the reference, and the URL of the page the quote is on when the reference had none. What the reference supports stays as a person wrote it.
2. **A new reference with a quote**, from another page the repository cites or an open-access work OpenAlex finds for the route: the citation from the repository's reference or OpenAlex's record, the URL, what it supports in the proposer's words, the quote, `status: unverified` and `proposed_by`.

Either way the reference stays `unverified` and the route stays in the queue; the queue's item says "A quote is ready to check" once one of its references has a quote.

**Code finds the passages** as for ore candidates: the route's own references' pages first, then the repository's other cited pages, then OpenAlex's open-access works for "<label> archaeology" and "<label> experimental archaeology". A sentence is offered if it is prose and names what the route makes (its thing and technique; for a route that does something, its tools and technique) and something it takes (its materials and tools, or what it does, from its label). Ranking and the other filters are 0048's.

**The proposer** (Sonnet, medium effort) reads the route as a person does (what it makes, what it takes and under what conditions, its notes and its references) and the numbered passages, each from the route's own references marked as such, and chooses one or says it is unsure. **The reviewer** (Sonnet, high effort) reads the route, the proposal and the page around the quote, with 0048's rules: the quote must carry the claim by itself, and a citation's style isn't objected to.

**Checks in code:** for a new reference, that the route doesn't already cite the work (same citation or URL) and that it says what it supports; for a quote on an existing reference, that it has none yet; and for both, that the site may be cited, the page loads, the quote is on it word for word, and the quote names what the route makes or uses.

**Route files are edited as text.** A reference is inserted as lines (or fields into one), each value a double-quoted scalar, and the file is parsed again: the edit is refused unless the only difference is the one intended. The gate validates the data (`capabilities validate`) before it builds.

**A reference records who proposed it.** `proposed_by` (the run, `routes-20261125-120000`) is an optional field of every reference; the app says "Proposed by an agent, run …" under it.

**No evaluation set.** Unlike ore candidates, routes have no answers a person already gave. A find-only run over every queued route (no plan usage) checks coverage and tunes the searches; the first ten-route pull request is the evaluation, its owner grading each quote.

**Out of scope:** the mining routes copied for each ore mineral (fixing the template fixes them; the pull request names a template's copies), proposing routes or requirements, and marking anything verified.

## Consequences

- A person checking a route starts from a sentence on a page instead of a book; the queue says which routes have one.
- The next agent task is a new `Task`, not a change to the run.
- A route can carry references no person chose; `proposed_by` says which, and the pull request is where a person rejects them.
- The proposer's "supports" for a new reference is a model's sentence, checked only by the reviewer and the person merging. A quote on an existing reference can't change what that reference says it supports.
- Text insertion depends on the layout the route files use (a top-level `references` list of `- citation:` items). The parse check refuses anything else, so an unusual file fails loudly instead of being rewritten.
- The Dagster op's name and config changed (`curate`, `task`, `names` for `minerals`): launch commands written for 0048 need the new names.

## Alternatives considered

- **Round-tripping the YAML with ruamel.yaml.** It loads and dumps a file keeping comments, but rewrote every flow mapping in all 54 route files (`{ role: tool }` to `{role: tool}`): each pull request would touch every requirement line.
- **Only new references.** Simpler, but it would miss the routes whose own works can be quoted, and add a second reference for a work the route already cites.
- **A formal evaluation** with the 20 `secondary` references hidden, to see whether agents quote the same pages for the same claims. It would cost plan usage the owner wants for later milestones, and a secondary reference's page is a summary, not the work: matching it says little about the quotes the task proposes.
- **Letting agents verify.** 0035 and 0047 keep `verified` for a person who read the work; an agent's reading is what this task offers them to check.
