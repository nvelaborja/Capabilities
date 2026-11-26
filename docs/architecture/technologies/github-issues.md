# GitHub issue forms and the issues API

## What it is

GitHub issues are the repository's tracker: numbered, public threads anyone with a GitHub account can open. An **issue form** is a YAML template that makes a new issue a form with named fields instead of a blank text box. The **issues API** is GitHub's REST endpoint for reading them as JSON. Together they are how a reader reports a wrong fact, and how the pipeline reads the reports ([ADR 0050](../../adr/0050-report-withdraw-and-recheck-agent-facts.md)).

## How it works

**Forms.** A form lives in `.github/ISSUE_TEMPLATE/<name>.yml`. Its top level gives a `name`, a `description`, a default `title` and `labels`, which GitHub adds to every issue made from it (a label that doesn't exist in the repository is left off). Its `body` is a list of elements: `markdown` (text shown to the reader), `input` (one line), `textarea`, `dropdown` and `checkboxes`, each with a `label`, an optional `description`, `validations` (`required: true`), and an `id`.

**Pre-filling from a link.** `https://github.com/<owner>/<repo>/issues/new?template=<name>.yml` opens a form, and further query parameters fill its fields: each is named by the field's `id`, which GitHub's form schema calls "the canonical identifier for the field in URL query parameter prefills". `title=` fills the title. The reader still writes and submits the issue on GitHub, signed in.

**The issue body.** When the form is submitted, GitHub turns the answers into the issue's Markdown body. In practice each field is a `### <label>` heading followed by its answer, and an empty optional field reads `_No response_`. GitHub's docs say only that the answers are "converted to markdown", so code reading them should expect that layout and fail softly if it changes.

**The issues API.** `GET /repos/{owner}/{repo}/issues` lists a repository's issues as JSON: `labels=` (comma-separated names), `state=` (`open`, the default, `closed` or `all`), `per_page=` (at most 100) and `page=`. It lists pull requests too, since GitHub counts every pull request as an issue: those have a `pull_request` key. Each issue has its `number`, `html_url`, `title`, `body`, `user`, `labels`, `state` and dates. Unauthenticated requests are limited to 60 an hour per IP address; a token raises that to 5,000.

## How we use it

- **Reports.** `.github/ISSUE_TEMPLATE/report.yml` is the report form, label `report`, with fields `fact`, `kind`, `reference`, `run` (which the app fills in), `problem` and `source` (which the reader writes). The detail pane's "Report a problem" links build its URL (`web/src/detail/report.ts`): every node, line, route and reference has one. The app sends and stores nothing.
- **Reading them.** The Dagster asset `upstream/github_reports` lists open issues labelled `report`, unauthenticated (one request per 100 reports, so far inside the limit), skips pull requests, reads the form's fields back from each body (`report_fields` in `upstream.py`) and keeps only the number, link, title, date and the four fields the app filled in, never who wrote it or what they wrote. Like every dataset it has a cold backup in `snapshots/`. The curation queue lists the reports first (`reported`).
- **Re-checks that fail.** With `report_failures: true`, the `agent_recheck` job opens an issue for each fact that doesn't hold, with `gh issue create --label report` and a body in the form's layout, so it is read back like a reader's report.
- **Closing.** A withdrawal's pull request says "Closes #<number>"; merging it closes the report, and the next download leaves it out.

## Where it lives

| What | Where |
|---|---|
| The report form | `.github/ISSUE_TEMPLATE/report.yml` |
| The report links | `web/src/detail/report.ts`, `ReportLink.tsx` |
| Reading the reports | `GitHubReports` and `report_fields` in `pipeline/src/capabilities_pipeline/upstream.py` |
| Reporting a failed re-check | `pipeline/src/capabilities_pipeline/agents/recheck.py` |
| A recording for tests | `pipeline/tests/fixtures/github-report-issues.json`, served by `github_endpoint` in `conftest.py` |

```bash
cd pipeline && uv run dg launch --assets 'upstream/github_reports'   # read the open reports
gh issue list --label report                                         # the same, by hand
```

## Things to know

- The `report` label must exist in the repository, or issues from the form arrive without it and the download, which asks for the label, misses them.
- The field `id`s are a contract between the form, the app's links and `REPORT_FIELDS` in `upstream.py`: rename one in all three.
- A reader can type anything into a field, or open an issue without the app's link. Nothing downstream tests what they wrote (a typo mustn't stop the build), and an issue that names no fact is queued on its own.
- Reports are public. Ask readers for facts and sources, never for anything personal.
- The repository's address is in `report.ts` and in `REPORTS.url`; a fork changes both.

## Further reading

1. [Syntax for issue forms](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-issue-forms): the top-level keys, `labels` among them.
2. [Syntax for GitHub's form schema](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-githubs-form-schema): each element, and `id` as the key for pre-filling.
3. [Creating an issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/creating-an-issue): "Creating an issue from a URL query".
4. [REST API endpoints for issues](https://docs.github.com/en/rest/issues/issues#list-repository-issues): "List repository issues".
5. [Rate limits for the REST API](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api).
