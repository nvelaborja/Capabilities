# 0048. Run curation agents through Claude Code on a Claude subscription, and start with ore candidates

- **Status:** Proposed
- **Date:** 2026-11-25
- **Supersedes:** in part [0035](0035-propose-curated-facts-with-audited-agents.md): its models and interfaces, its spending caps and API rate limits, and where the audit log lives

## Context

[0035](0035-propose-curated-facts-with-audited-agents.md) decided that agents propose curated facts, code and a reviewer agent check them, and a person merges a pull request. It assumed the Claude API: each step a Dagster asset calling it with server-side web search and fetch, a spending cap per run, API rate limits, and the Message Batches API for large batches.

The project has no API budget. Its owner has a Claude Pro subscription, and wants agent runs to draw on that plan's usage, ideally hundreds of items without going past the five-hour limit. What we found on 2026-11-24 (Claude Code 2.1.330):

- **Claude Code can be scripted on a subscription login.** `claude -p` (print mode) runs one task and exits; it uses the Claude login unless an API key is set (`ANTHROPIC_API_KEY` takes precedence, and would bill the API). `--bare` skips the login, so it can't be used. `claude auth status` says which login is in use (`authMethod: claude.ai`, `subscriptionType: pro`).
- **It can return structured output** (`--json-schema`, the answer in `structured_output`), limit turns (`--max-turns`), offer only the tools named (`--tools`, `--allowedTools`), and run without CLAUDE.md, plugins, hooks or MCP servers (`--safe-mode`, `--strict-mcp-config`). With `--output-format stream-json --verbose` it prints every event: the tools used and their inputs, token usage, and an API-equivalent cost (`total_cost_usd`), which a subscription doesn't charge.
- **It reports the plan's usage.** Each call prints a `rate_limit_event` with the share used of the five-hour and weekly windows (`unifiedWindows.five_hour.utilization`, 0 to 1). Anthropic doesn't publish the limits themselves for Pro, only that they are shared between claude.ai and Claude Code.
- **Its web fetch returns a model's reading of a page, not the page.** A quote the agent copies through it can be a paraphrase.
- **Anthropic's terms for the Agent SDK** say third-party products may not offer claude.ai login to their users. Scripting one's own Claude Code for one's own non-commercial project isn't addressed in what we read; the owner judges that.

## Decision

**Each agent step is one `claude -p` run** on the owner's Claude login, started by the pipeline as a subprocess. Every call:

- runs in an empty temporary directory with `--safe-mode`, `--strict-mcp-config` and `--no-session-persistence`, its own system prompt, a turn limit, and a JSON Schema for its answer;
- gets only its role's tools: the proposer web search and web fetch, the reviewer none;
- takes its prompt on stdin, and prints stream-json, which the pipeline reads for the answer, the tools used, the usage and the plan's limits.

**A run refuses to start on anything but a Claude login.** If `ANTHROPIC_API_KEY` (or another credential that would take precedence) is set, or `claude auth status` reports anything but `claude.ai`, it stops before spending anything. It never turns on paid extra usage.

**Runs are sized by items and stopped by the plan's usage, not by dollars.** A run names how many items to work through, one at a time. Before each item it compares the usage last reported with two thresholds (by default 80% of the five-hour window and 90% of the weekly one) and stops if either is passed; if the limit is reached mid-item, it stops at once. Either way, the rest stay in the queue, and what was accepted so far still goes to a pull request. Concurrency is one: the owner's own use of Claude shares the same limits. The API-equivalent cost is recorded to compare prompts and models, not as a budget.

**The run is a Dagster job, `agent_curation`, launched by hand** with its size (`dg launch --job agent_curation --config-json …`). It is not an asset, so materializing everything never starts one.

**The first task is ore candidates** ([0045](0045-bring-ore-minerals-in-from-upstream-roast-sulphides-and-queue-the-gaps.md)): for each mineral MRDS lists on many copper, iron and tin deposits, propose its ore crosswalk row.

1. **Propose.** The proposer (Opus 5.5 to start) researches the mineral and answers with a Wikidata item, an ore class or `none`, one source (citation and URL), a quote from it word for word, what it supports, and a short note, or `unsure`. Code fills in the rest: the id (from MRDS's name) and the route it is mined like (the one the crosswalk's rows of that class use). A class no row uses yet (tin ore today) is left to a person.
2. **Check mechanically.** Code checks the class; the Wikidata item (it exists, wasn't merged, its label or an alias is the mineral's name, and no crosswalk has it yet); the id is new; the source isn't one whose data may not be used (Mindat); and, downloading the cited page itself (HTML, PDF or plain text), that it loads, that the quote is on it word for word (ignoring case and typography; "…" may leave words out) and that the quote names the mineral.
3. **Challenge.** The reviewer (Opus 5.5) gets the proposal, the Wikidata item and the text around the quote, all as the pipeline downloaded them, and none of the proposer's searches or reasoning. It answers accept, revise or reject, with objections tied to parts of the proposal.
4. A failed check or a "revise" goes back to the proposer with the reasons. Each item gets two proposals at most.
5. **Gate.** Accepted rows are written into the crosswalk in a temporary git worktree on a new branch, `agents/<run>`, from `origin/main`. There Wikidata's labels and quantities for the new items, and OpenAlex and Crossref for the new citations ([0047](0047-check-citations-against-openalex-and-crossref.md)), are downloaded as they would be by hand, and the graph is built with all its tests. A row whose cited work is `found` or `review_found`, or is a web page whose link works, passes; any other result drops the row, and the rest are checked again. A row rejecting a mineral (class `none`) builds nothing, so its reference isn't looked up; its page and quote were checked all the same.
6. **Pull request.** What passes is committed with the refreshed cold backups, the regenerated works cited and the run's summary, pushed, and opened as a **draft** pull request with the owner's `gh` login, titled "Agent proposals: …". The run never merges.

**The crosswalk gains two columns**: `quote`, the passage word for word, and `proposed_by`, the run. An agent's row leaves `status` empty, so its reference is `unverified` ([0008](0008-record-the-basis-of-every-number.md)); passing the agents' review isn't reading the work. The build carries the quote into the mineral's reference (the reference schema gains an optional `quote`), and `proposed_by` into the provenance of the mineral, its deposit and its route. The app's detail pane shows the quote under the reference, and "Proposed by an agent, run …" beside where the node came from.

**The audit log is an append-only DuckDB file, `audit/agents.duckdb`, kept out of git.** Its tables (`run_starts`, `calls`, `checks`, `outcomes`, `run_ends`) only ever gain rows: every call with its prompt, prompt version (the prompt file's hash), model and settings, the answer, every tool call, the usage, the plan's limits and the events printed; every check; every outcome (a later outcome of an item supersedes an earlier one). The login is recorded only as its method and plan, never the account. Each run's summary is written beside it (`audit/runs/<run>.json`) and, for a run that opens a pull request, committed with it (`data/agent_runs/<run>.json`), so what was merged is explained even if the audit file is lost.

**An evaluation run asks the agents again about the minerals a person already decided** (the ten rows reviewed by hand, kept in `pipeline/src/capabilities_pipeline/agents/evaluation/ore_candidates.csv`), treating those rows as undecided. It goes through every step, the gate included, opens no pull request, and scores the answers against the person's: how many were right, how many were accepted, and above all how many accepted were wrong. The first run is an evaluation, to measure both the quality and how much of the plan an item uses before running real queue items.

## Consequences

- Runs cost no money and need no API key, but they share the owner's plan with their own use of Claude. How many items fit in five hours isn't published anywhere; the evaluation measures it, and each run records the plan's usage before and after.
- Usage, not dollars, now bounds a run. The thresholds stop a run before the owner is locked out of Claude for the rest of the window.
- One item at a time is slow. Nothing urgent depends on it.
- A quote must be copied exactly through a fetch tool that summarises. Expect paraphrases to be sent back at first; the prompt tells the proposer to ask for exact sentences.
- The gate downloads the reference candidates in full (about a minute and a half, and about $0.03 of OpenAlex's free $0.10 a day), so a few runs a day stay within the free allowance.
- The pull request carries refreshed cold backups of three datasets, as any change to the crosswalk would.
- The report button, withdrawal, and batch re-checks by run ([0035](0035-propose-curated-facts-with-audited-agents.md)) are still to come, as are sources for routes with only unverified references.
- Whether this use of a subscription is within Anthropic's terms is the owner's call; if it isn't, the same pipeline can call the API by swapping how a step is asked.

## Alternatives considered

- **The Claude API, as 0035 planned.** Server-side tools, batches and exact pages from its fetch tool, but it bills per token, and there is no budget for it.
- **The Claude Agent SDK.** It drives the same agent loop from Python, but its documentation asks for an API key and says third-party products may not use claude.ai login. The CLI is the documented way to use a subscription without a key.
- **Let the agent's fetch tool be trusted for quotes.** Simpler, but it would let a paraphrase or an invented sentence through, which is exactly what 0035's mechanical checks are for.
- **Run items in parallel.** Faster, but it would burn through the shared limits in bursts and make the thresholds coarse.
- **A spending cap from `--max-budget-usd`.** It caps the API-equivalent cost, which a subscription doesn't charge; the plan's usage, which it does count, is what a run must stay under.
- **Let the agent choose the route a mineral is mined like.** It is mechanical, given the class, so code does it.
- **Keep the audit log in the warehouse** (`build/warehouse.duckdb`), as 0035 suggested. Everything in `build/` is generated and may be deleted at any time; the audit log must outlive every build.
