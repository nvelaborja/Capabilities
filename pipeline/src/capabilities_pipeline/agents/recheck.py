"""Re-checking facts agents proposed that a person merged (ADR 0035, ADR 0050). Started by an admin, by hand, as the
Dagster job `agent_recheck`; nothing in the app starts one.

The facts are chosen by the run that proposed them, or by a prompt version or a model the run used (from the summaries
in data/agent_runs/), or all of them. Each is checked again as the proposal it was, on its item as it was before: code's
checks always (the site may be cited, the page still loads, the quote is still on it word for word and names its
subject; free), and the reviewer agent only if the admin asks (it uses the Claude plan, like a run). A re-check changes
no data. What fails is in its summary and the audit log; with `report_failures` each becomes a GitHub issue labelled
`report`, which joins the curation queue like a reader's report, for a person to withdraw or keep. A fact that couldn't
be checked (a site didn't answer, or the reviewer couldn't be asked) is listed as not re-checked, and never reported.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from capabilities.withdraw import AGENT_RUNS

from ..build import git_commit
from ..upstream import report_fields
from .audit import AUDIT_FILE, AuditLog, audit_dir_for
from .branch import BranchError, Downloads, check_gh, run_command
from .claude import AgentError, UsageLimitReached, check_login
from .curate import Curator, Settings, new_run_id
from .ore_candidates import OreCandidates
from .route_sources import RouteSources
from .sources import Library, known_sources
from .task import Check, Merged, Task, cell
from .web import Web

TASKS = (OreCandidates, RouteSources)
# What a fact can come to. Only the first two say something is wrong with it; the last two say it couldn't be checked.
REPORTED = ("fails", "objected")
NOT_RECHECKED = ("unreachable", "failed")


@dataclass(frozen=True)
class RecheckSettings:
    # Which facts: those from these runs, or from runs that used these prompt versions or models; or every one.
    runs: tuple[str, ...] = ()
    prompt_versions: tuple[str, ...] = ()
    models: tuple[str, ...] = ()
    every_fact: bool = False
    # Ask the reviewer agent again too: uses the plan. Off, a re-check costs nothing but downloads.
    reviewer: bool = False
    reviewer_model: str = "sonnet"
    reviewer_effort: str | None = "high"
    stop_at_five_hour: float = 0.8
    stop_at_seven_day: float = 0.9
    # Open a GitHub issue labelled `report` for each fact that fails, unless one is open for it already.
    report_failures: bool = False
    claude_command: str = "claude"
    gh_command: str = "gh"

    def __post_init__(self):
        if not (self.runs or self.prompt_versions or self.models or self.every_fact):
            # Without one, a slip in the config would re-check, and with the reviewer pay for, every fact.
            raise ValueError("name the runs, prompt versions or models whose facts to re-check, or set every_fact")


@dataclass
class FactResult:
    fact: Merged
    task: str
    # holds; fails (a check failed); objected (the reviewer asked for changes or rejected it); unreachable (a check
    # failed only because a site didn't answer); failed (the reviewer couldn't be asked)
    outcome: str
    checks: list[Check] = field(default_factory=list)
    review: dict | None = None
    reported: str | None = None  # the issue opened for it

    def summary(self) -> dict:
        return {"fact": self.fact.fact, "item": self.fact.item.name, "task": self.task, "run": self.fact.run,
                "subject": self.fact.subject, "outcome": self.outcome,
                "failed_checks": [asdict(c) for c in self.checks if not c.passed], "review": self.review,
                "reported": self.reported}


def recheck(root: Path, settings: RecheckSettings, downloads: Downloads = Downloads(), web: Web | None = None,
            on_progress: Callable[[str], None] = print, audit_dir: Path | None = None) -> dict:
    """Re-check the facts the settings choose. Returns the summary, also kept in the audit directory."""
    login = check_login(settings.claude_command) if settings.reviewer else {}
    if settings.report_failures:
        check_gh(settings.gh_command)
    web = web or Web(wikidata_url=downloads.wikidata_site_url, openalex_url=downloads.openalex_url)
    library = Library(web, known_sources(root))
    runs = chosen_runs(root, settings)
    recheck_id = new_run_id("recheck")
    audit_dir = audit_dir or audit_dir_for(root)
    results: list[FactResult] = []
    curators: list[Curator] = []
    stopped = failed = None
    with AuditLog(audit_dir / AUDIT_FILE) as audit:
        audit.run_started(recheck_id, "recheck", "checks and review" if settings.reviewer else "checks",
                          asdict(settings), login, git_commit(root))
        try:
            stopped = _recheck_facts(root, settings, library, runs, recheck_id, audit, on_progress, results, curators)
            if settings.report_failures:
                _report(root, results, recheck_id, settings.gh_command, on_progress)
        except BaseException as error:
            # Whatever stops it (a bug, Dagster terminating it, ^C), what it checked so far is still recorded.
            failed = f"{type(error).__name__}: {error}"
            raise
        finally:
            summary = _summary(recheck_id, settings, results, stopped or failed, curators)
            audit.run_ended(recheck_id, stopped or failed, summary["outcomes"], None, summary["usage"])
            path = audit_dir / "rechecks" / f"{recheck_id}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def _recheck_facts(root: Path, settings: RecheckSettings, library: Library, runs: set[str] | None, recheck_id: str,
                   audit: AuditLog, on_progress: Callable[[str], None], results: list[FactResult],
                   curators: list[Curator]) -> str | None:
    """Re-check each chosen fact, adding to `results` as it goes; returns why it stopped early, if it did."""
    for task_class in TASKS:
        task = task_class.before_merging(root, library)
        curator = Curator(recheck_id, _curator_settings(settings, task.name), task, audit, on_progress)
        curators.append(curator)
        for fact in task.merged():
            if runs is not None and fact.run not in runs:
                continue
            if stopped := next((why for c in curators if (why := c.over_limit())), None):
                return stopped
            try:
                results.append(_recheck(fact, task, curator if settings.reviewer else None, audit, recheck_id))
            except UsageLimitReached as error:
                return str(error)
            on_progress(f"{fact.fact}: {results[-1].outcome}")
    return None


def chosen_runs(root: Path, settings: RecheckSettings) -> set[str] | None:
    """The runs whose facts to re-check, from the runs named and the summaries of those that used the prompts or
    models named; None for every run."""
    if settings.every_fact:
        return None
    runs = set(settings.runs)
    for path in sorted((root / AGENT_RUNS).glob("*.json")):
        summary = json.loads(path.read_text(encoding="utf-8"))
        used_prompts = set((summary.get("prompts") or {}).values())
        used_models = set((summary.get("models") or {}).values()) | set((summary.get("model_ids") or {}).values())
        if used_prompts & set(settings.prompt_versions) or used_models & set(settings.models):
            runs.add(summary["run"])
    return runs


def _recheck(fact: Merged, task: Task, curator: Curator | None, audit: AuditLog, recheck_id: str) -> FactResult:
    # Code's checks need no finding: they check the proposal against its page and item, not the passages offered.
    checks, evidence = task.check(fact.item, fact.proposal, None)
    # Logged under the item's name, as the reviewer's call is, so that everything about a fact is found together.
    for check in checks:
        audit.check(recheck_id, fact.item.name, 1, check.name, check.passed, check.detail)
    result = FactResult(fact, task.name, _outcome_of(checks), checks)
    if curator and result.outcome == "holds":
        try:
            result.review = curator.review(fact.item, 1, fact.proposal, evidence)
        except UsageLimitReached:
            raise
        except AgentError as error:
            result.outcome, result.review = "failed", {"error": str(error)}
        else:
            if result.review["verdict"] != "accept":
                result.outcome = "objected"
    audit.outcome(recheck_id, fact.item.name, result.outcome, _why(result), None)
    return result


def _outcome_of(checks: list[Check]) -> str:
    failed = [check for check in checks if not check.passed]
    if not failed:
        return "holds"
    # A site that didn't answer says nothing about the fact; any other failure does, whatever else was down.
    return "unreachable" if all(check.unreachable for check in failed) else "fails"


def _why(result: FactResult) -> str:
    failed = [f"- {c.name}: {c.detail}" for c in result.checks if not c.passed]
    if failed and result.outcome == "unreachable":
        return "A site didn't answer, so it couldn't be re-checked:\n" + "\n".join(failed)
    if failed:
        return "It failed these checks:\n" + "\n".join(failed)
    if result.review and result.review.get("verdict") not in (None, "accept"):
        objections = "\n".join(f"- {o['about']}: {o['objection']}" for o in result.review.get("objections") or [])
        return f"The reviewer: {result.review['verdict']}. {result.review.get('summary', '')}\n{objections}".strip()
    if result.review and "error" in result.review:
        return f"The reviewer couldn't be asked: {result.review['error']}"
    return "Every check passed" + (", and the reviewer accepted it." if result.review else ".")


def _report(root: Path, results: list[FactResult], recheck_id: str, gh: str, on_progress: Callable[[str], None]):
    """An issue labelled `report` for each fact found wrong, in the report form's shape, so the next build queues it;
    none for a fact an open report already names, whether a reader's or an earlier re-check's."""
    try:
        reports = [report_fields(issue.get("body") or "") for issue in json.loads(run_command([
            gh, "issue", "list", "--label", "report", "--state", "open", "--limit", "500", "--json", "body"], root))]
    except BranchError as error:
        on_progress(f"Couldn't list the open reports, so none were opened: {error}")
        return
    for result in results:
        if result.outcome not in REPORTED:
            continue
        if any(_names(report, result.fact) for report in reports):
            result.reported = "already reported"
            continue
        try:
            result.reported = run_command([gh, "issue", "create", "--label", "report", "--title",
                                           f"Re-check: {result.fact.fact} doesn't hold",
                                           "--body", report_body(result, recheck_id)], root)
        except BranchError as error:
            on_progress(f"Couldn't report {result.fact.fact}: {error}")


def _names(report: dict[str, str], fact: Merged) -> bool:
    """Whether an open report is about this fact: the same mineral or route, and for a reference, the same one (a
    report on a route as a whole may be about any of its references)."""
    if _plain(report.get("fact", "")) != _plain(fact.subject):
        return False
    return fact.kind != "reference" or _plain(report.get("reference", "")) == _plain(fact.citation)


def _plain(text: str) -> str:
    # Undoes what cell() does to a re-check's own report, so it compares equal to what the app filled in.
    return " ".join(text.replace("\u2060", "").replace("\\|", "|").split()).casefold()


def report_body(result: FactResult, recheck_id: str) -> str:
    """The report form's fields (.github/ISSUE_TEMPLATE/report.yml), as GitHub writes them for a form."""
    fact = result.fact
    return "\n\n".join([
        "### Fact", cell(fact.subject), "### Kind", fact.kind, "### Reference", cell(fact.citation) or "_No response_",
        "### Agent run", fact.run, "### What is wrong",
        f"Re-check `{recheck_id}`: {cell(_why(result))}", "### A better source", "_No response_",
    ]) + "\n"


def _curator_settings(settings: RecheckSettings, task: str) -> Settings:
    return Settings(task=task, reviewer_model=settings.reviewer_model, reviewer_effort=settings.reviewer_effort,
                    stop_at_five_hour=settings.stop_at_five_hour, stop_at_seven_day=settings.stop_at_seven_day,
                    claude_command=settings.claude_command, pull_request=False)


def _summary(recheck_id: str, settings: RecheckSettings, results: list[FactResult], stopped: str | None,
             curators: list[Curator]) -> dict:
    outcomes: dict[str, int] = {}
    for result in results:
        outcomes[result.outcome] = outcomes.get(result.outcome, 0) + 1
    # Each task's reviewer is its own; the plan's usage is the last any of them saw.
    usage = {curator.task.name: asdict(curator.usage) for curator in curators}
    return {
        "recheck": recheck_id,
        "finished_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "settings": asdict(settings),
        "stopped_because": stopped,
        "outcomes": outcomes,
        "not_rechecked": [result.fact.fact for result in results if result.outcome in NOT_RECHECKED],
        "usage": usage,
        "facts": [result.summary() for result in results],
    }
