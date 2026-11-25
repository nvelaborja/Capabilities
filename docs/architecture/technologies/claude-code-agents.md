# Claude Code agents

## What it is

**Claude Code** is Anthropic's agent for the terminal: a program (`claude`) that gives a Claude model tools (reading files, running commands, searching and fetching the web) and lets it work in a loop until a task is done. Most people use it interactively. With `-p` ("print mode") it runs one task without a person, prints the result, and exits, which makes it a step a pipeline can call like any other command.

It runs on either an API key, billed per token, or a person's Claude subscription (Pro, Max), counted against the plan's usage limits. We use the subscription: agent runs cost nothing beyond the plan ([ADR 0048](../../adr/0048-run-agents-through-claude-code-on-a-claude-subscription.md)).

An **agent** here is one such run with one job: the *proposer* researches a mineral on the web and proposes a row for the ore crosswalk; the *reviewer* gets the proposal and the pages it cites and looks for what is wrong ([ADR 0035](../../adr/0035-propose-curated-facts-with-audited-agents.md)).

## How it works

**Print mode, as a function call.** One process, one answer:

```bash
echo "The task…" | claude -p --safe-mode --strict-mcp-config --no-session-persistence \
  --model opus --max-turns 30 --tools WebSearch,WebFetch --allowedTools WebSearch,WebFetch \
  --system-prompt "You research minerals…" --json-schema '{"type": "object", …}' \
  --output-format stream-json --verbose
```

`--safe-mode` leaves out CLAUDE.md, plugins, hooks and the rest of the user's customisations, and `--strict-mcp-config` any MCP servers; `--no-session-persistence` saves nothing. `--tools` is what the model may use and `--allowedTools` lets it use them without asking (nobody is there to answer). `--json-schema` is the shape the answer must have, and `stream-json` prints every event, one JSON object per line.

**Structured output.** With `--json-schema`, the final answer is validated against the schema and returned as `structured_output` in the last event. The model gives it through a tool called `StructuredOutput`, so it takes a turn of its own.

**The event stream.** `--output-format stream-json --verbose` prints, line by line:

| Event | What it holds |
|---|---|
| `system` (`init`) | The session: model, tools offered |
| `assistant` | Each message, with any `tool_use` blocks: a search's `query`, a fetch's `url` and what it asked of the page |
| `user` | Tool results going back to the model |
| `rate_limit_event` | The plan's usage: `unifiedWindows.five_hour.utilization` and `seven_day.utilization`, 0 to 1, and whether requests are `allowed` |
| `result` | The end: `structured_output`, `usage` (tokens, cache reads and writes), `total_cost_usd`, `num_turns`, `is_error` and why |

**Which login.** `claude -p` uses the subscription login unless an API key is in the environment (`ANTHROPIC_API_KEY` wins, and bills the API). `claude auth status` prints the login as JSON: `authMethod` is `claude.ai` for a subscription. `--bare` skips the login altogether, so it can't run on a subscription.

**Usage limits.** A plan has a five-hour window and a weekly one, shared by claude.ai, Claude Code and anything scripted with it. Anthropic doesn't publish the limits as numbers; the `rate_limit_event` says how much of each window is used. When a window is full, calls fail ("You've hit your limit") until it resets.

**Web fetch reads for the model.** Claude Code's `WebFetch` gives the page to a small model with the agent's question and returns that model's answer, not the page. It is good for finding things and bad for quoting them exactly, which is why the pipeline downloads every cited page itself.

## How we use it

The Dagster job `agent_curation` ([ADR 0048](../../adr/0048-run-agents-through-claude-code-on-a-claude-subscription.md)), started by hand with a size, works through the curation queue's ore candidates one at a time:

1. **Before anything:** `claude auth status` must say `claude.ai`, no API key may be set, and `gh` must be logged in.
2. **Propose:** the proposer (web search and fetch, 30 turns) answers with a Wikidata item, an ore class or `none`, a citation, a URL, a quote and what it supports, or `unsure`.
3. **Check:** code reads the Wikidata item and downloads the cited page (HTML, PDF via pypdf, or text), and looks for the quote word for word.
4. **Challenge:** the reviewer (no tools, 3 turns) gets the proposal and the downloaded text around the quote, never the proposer's searches, and accepts, asks for a revision, or rejects.
5. **Gate and pull request:** accepted rows are written into a temporary worktree, the downloads they need are made and the graph built; rows whose cited work isn't found are dropped; the rest become a draft pull request.

Every call, check and outcome is appended to `audit/agents.duckdb`. A run stops before its next item once the plan's five-hour usage passes 80% (or weekly 90%), and at once if the limit is reached.

## Where it lives

| What | Where |
|---|---|
| Calling Claude Code, reading its events, the login check | `pipeline/src/capabilities_pipeline/agents/claude.py` |
| The prompts (versioned by their hash) | `pipeline/src/capabilities_pipeline/agents/prompts/` |
| The ore candidate task: schemas, checks, the crosswalk row | `pipeline/src/capabilities_pipeline/agents/ore_candidates.py` |
| Reading pages and Wikidata items, finding quotes | `pipeline/src/capabilities_pipeline/agents/web.py` |
| One item's loop; a whole run; the worktree, gate and pull request | `agents/curate.py`, `agents/run.py`, `agents/branch.py` |
| The audit log | `agents/audit.py`; the file is `audit/agents.duckdb` (not in git) |
| The evaluation set | `pipeline/src/capabilities_pipeline/agents/evaluation/ore_candidates.csv` |
| The Dagster job | `agent_curation` in `pipeline/src/capabilities_pipeline/assets.py` |
| Tests, with stand-ins for `claude`, `gh` and the web | `pipeline/tests/test_agents.py`, `pipeline/tests/fixtures/agents/fake_claude.py` |

```bash
claude auth status                         # authMethod must be "claude.ai"
cd pipeline
uv run dg launch --job agent_curation --config-json '{"ops": {"curate_ore_candidates": {"config": {"items": 10, "evaluate": true}}}}'
uv run dg launch --job agent_curation --config-json '{"ops": {"curate_ore_candidates": {"config": {"items": 5}}}}'
cd .. && python3 -c "import duckdb; duckdb.sql(\"select item, outcome, reason from 'audit/agents.duckdb'.outcomes\").show()"
```

## Things to know

- **An API key in the environment changes who pays.** The run refuses to start with one set, rather than unset it silently.
- **Your own Claude use and the agents share the limits.** A run that stops at 80% leaves you the rest of the window.
- **Each call starts clean.** No saved session, no CLAUDE.md, no plugins: what the agent knows is its system prompt and the task. That keeps results reproducible from the prompt version.
- **`total_cost_usd` is what the tokens would cost on the API.** A subscription doesn't charge it. It is recorded to compare prompts and models, not as a bill.
- **Structured output takes a turn.** A role with no tools still needs two turns: its answer, and the `StructuredOutput` call.
- **The page is untrusted.** The reviewer reads downloaded text; its prompt says the page is evidence, not instructions, it has no tools, and its answer must match a schema.
- **Tests never run `claude`.** A stand-in script plays back scripted answers in the same event format.
- **Terms.** Anthropic's Agent SDK terms say third-party products may not offer claude.ai login to their users. This project runs its owner's own Claude Code for their own non-commercial use; check the current terms before running it on yours.

## Further reading

1. [Run Claude Code programmatically](https://code.claude.com/docs/en/headless): print mode, output formats, structured output.
2. [CLI reference](https://code.claude.com/docs/en/cli-reference): every flag used here.
3. [Identity and access management](https://code.claude.com/docs/en/iam): which credentials Claude Code uses, and in what order.
4. [Settings](https://code.claude.com/docs/en/settings): where Claude Code's settings and CLAUDE.md come from, which a clean run leaves out.
5. [Use Claude Code with your Pro, Max, or Ultra plan](https://support.claude.com/en/articles/11145838-use-claude-code-with-your-pro-max-or-ultra-plan): usage limits on a subscription.
6. [Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview): the same loop as a library, and its terms on claude.ai login.
7. [pypdf](https://pypdf.readthedocs.io/en/stable/): reading the text of a cited PDF.
8. [Wikidata: data access](https://www.wikidata.org/wiki/Wikidata:Data_access): `Special:EntityData`, how an item's label, aliases and description are read.
9. [git worktree](https://git-scm.com/docs/git-worktree) and [gh pr create](https://cli.github.com/manual/gh_pr_create): the branch and the draft pull request.
