# 0050. Report facts as GitHub issues, withdraw agents' facts into a file, and re-check them only when an admin asks

- **Status:** Accepted
- **Date:** 2026-11-26

## Context

[0035](0035-propose-curated-facts-with-audited-agents.md) lets agents' facts merge before a person has read every source, on condition that mistakes can be found and removed: anyone can report a fact from the app; withdrawing one is a pull request that removes or suppresses it; every report and withdrawal is linked to the run that produced the fact; and one bad fact means re-checking everything from the same run, prompt version or model.

Agents' facts are now in the data: ore crosswalk rows ([0048](0048-run-agents-through-claude-code-on-a-claude-subscription.md)), and references and quotes on routes ([0049](0049-have-agents-quote-sources-for-unverified-routes.md)). Each carries `proposed_by`, its run, whose summary (prompt versions, models, and what it changed) is committed in `data/agent_runs/`. Nothing yet let a reader say a fact is wrong, or the owner take a run's facts out or check them again.

The app has no server of its own beyond the local one, and no accounts.

## Decision

**A report is a GitHub issue.** Every node, line, route and reference in the detail pane has a "Report a problem" link to a new issue on the report form (`.github/ISSUE_TEMPLATE/report.yml`, label `report`), with the fact's id, its kind, a reference's citation and the agent run filled in. The app sends and stores nothing; a reader needs a GitHub account. Any fact can be reported, a person's as well as an agent's.

**Open reports are an upstream dataset, and the queue's first kind.** `github_reports` is downloaded by Dagster from GitHub's issues API, like every dataset, with a cold backup ([0044](0044-require-every-upstream-dataset-with-cold-backups-in-git.md)). It keeps each open issue's number, link, title and date, and the fields the app filled in, never who reported it or what they wrote, which stay on GitHub. The curation queue gains `reported`, one item per fact listing its issues, ahead of every other kind: a report is someone telling us the graph is wrong.

**Withdrawing removes an agent's fact entirely and records it in `data/withdrawals.csv`.** `uv run capabilities withdraw ore <mineral>` or `withdraw reference <route> --citation …`, with `--reason` and optionally `--report <issue>`, removes an agent's ore row, an agent's reference, or an agent's quote on a person's reference (with the URL it brought, as the run's summary records). The file keeps what the fact said (its quote, citation and URL), its run, the reason and the report, so the record survives the fact. The change is opened as a pull request like any other, closing the issue. A person's own fact is corrected by editing it: the command refuses one.

**A withdrawn fact stays withdrawn.** `validate` refuses a withdrawn quote back on the same mineral or route, and agents' checks refuse proposing it (`quote_not_withdrawn`). A person can still cite the same work for another passage.

**A re-check runs only when an admin starts it.** The Dagster job `agent_recheck`, launched by hand, chooses merged agent facts by run, by a prompt version or model their run used, or all of them (one must be named). Each fact is checked again as the proposal it was, on its item as it was before: code's checks (the site, the page loads, the quote is on it word for word and names its subject) always, and the reviewer agent only when the admin sets `reviewer: true`, using the Claude plan with the run's usage limits. Nothing in the app starts one. A re-check changes no data: its results are in its summary (`audit/rechecks/`) and the audit log, as a run of its own. With `report_failures: true`, each fact that fails becomes a `report` issue in the form's shape, unless one is open for it already, so it joins the queue like a reader's report.

## Consequences

- A reader can say a fact is wrong in two clicks, and the owner sees it at the top of the queue after the next build.
- Withdrawals are in git, reviewed as pull requests, and labelled examples of agents' failures, as 0035 hoped.
- Reports need a GitHub account, and are public. A form in the app can replace the link later without changing the queue, which reads the issues.
- The repository's GitHub address is in two places: the web app's report link and the dataset's URL.
- The queue lists every open report, including ones that are wrong or duplicates; closing the issue takes it off.
- A free re-check catches pages that changed or went away and quotes no longer on them. Only one with the reviewer catches a quote that is still there but doesn't support the claim, and that uses the plan.
- An ore row's re-check needs Wikidata; a route fact's needs its run's summary in `data/agent_runs/`, without which it can't be rebuilt and is left out.

## Alternatives considered

- **A report form in the app, written to a file by the server.** No GitHub account needed, but the server is local only until the app is hosted, and the reports would need their own storage and review.
- **Marking a fact `withdrawn` instead of removing it.** Keeps the fact where it was, but every reader of the data, the reasoner and the app would have to leave it out.
- **Suppressing an agent's fact like an upstream record** (`data/suppressions/`). Suppressions leave out records of upstream datasets; an agent's fact is curated data, and removing it is simpler than keeping it and its suppression.
- **Re-checking on a schedule, or when a report arrives.** The owner wants plan usage spent only when they choose, and a report is read by a person first.
- **Always asking the reviewer.** About 0.2–0.3 points of the five-hour window per fact; code's checks are free and catch the commonest decay, a changed page.
