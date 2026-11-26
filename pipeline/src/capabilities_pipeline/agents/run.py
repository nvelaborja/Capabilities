"""Running an agent task, start to finish: what the Dagster job `agent_curation` calls (ADR 0048, ADR 0049).

1. Check, before anything is spent, that Claude Code is on the user's Claude login (and `gh` logged in, if the run is
   to open a pull request).
2. Take the first items: from the curation queue, or, for an evaluation, the items a person already decided.
3. Work through them one at a time (curate.py), stopping before the plan's usage limits.
4. Check the accepted changes in a temporary worktree, and open a draft pull request with those that pass (branch.py).
   An evaluation opens none: it scores the agents' answers against the person's.
5. Record the run's end in the audit log, and write its summary.
"""

from __future__ import annotations

import json
from collections import Counter
import tempfile
import urllib.error
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from capabilities.built import current_graph, load_queue

from ..build import BuildError, git_commit
from .audit import AUDIT_FILE, AuditLog, audit_dir_for
from .branch import BranchError, Downloads, Proposals, Worktree, check_gh, gate, publish, work_check
from .claude import UsageLimitReached, check_login
from .curate import Curator, ItemResult, Settings, new_run_id
from .ore_candidates import OreCandidates
from .route_sources import RouteSources
from .sources import Library, SourcesUnavailable, known_sources
from .task import Item, Task, cell
from .web import Web

TASKS = {task.name: task for task in (OreCandidates, RouteSources)}


@dataclass
class RunReport:
    run_id: str
    results: list[ItemResult]
    stopped_because: str | None
    pull_request: str | None
    summary: dict = field(repr=False, default_factory=dict)


def run_agents(root: Path, build_dir: Path, settings: Settings, downloads: Downloads = Downloads(),
               web: Web | None = None, on_progress: Callable[[str], None] = print,
               audit_dir: Path | None = None) -> RunReport:
    """One run. The audit log and run summaries go in `audit_dir`, by default audit/ in the repository."""
    web = web or Web(wikidata_url=downloads.wikidata_site_url, openalex_url=downloads.openalex_url)
    return Run(root, settings, downloads, web, on_progress, audit_dir or audit_dir_for(root)).execute(build_dir)


class Run:
    def __init__(self, root: Path, settings: Settings, downloads: Downloads, web: Web,
                 on_progress: Callable[[str], None], audit_dir: Path):
        self.root, self.settings, self.downloads, self.web, self.on_progress = root, settings, downloads, web, on_progress
        self.audit_dir = audit_dir
        if settings.task not in TASKS:
            raise ValueError(f"no task {settings.task!r}: one of {', '.join(TASKS)}")
        self.task_class = TASKS[settings.task]
        self.run_id = new_run_id(self.task_class.run_prefix)
        self.mode = "evaluate" if settings.evaluate else "propose"
        self.started_at = _now()
        self.results: list[ItemResult] = []
        self.stopped: str | None = None
        self.unpublished: str | None = None  # why accepted rows weren't checked together or published, if they weren't
        self.failed: str | None = None  # the error that ended the run early, if one did
        self.not_evaluated: list[str] = []  # items named for an evaluation that it has no answer for
        self.answers: dict[str, dict] = {}

    @property
    def opens_pull_request(self) -> bool:
        return self.settings.pull_request and not self.settings.evaluate and not self.settings.find_only

    def execute(self, build_dir: Path) -> RunReport:
        self.login = check_login(self.settings.claude_command)
        if self.opens_pull_request:
            check_gh(self.settings.gh_command)
        items = self._items(build_dir)
        pull_request = None
        with AuditLog(self.audit_dir / AUDIT_FILE) as audit:
            self.curator = Curator(self.run_id, self.settings, self.task, audit, self.on_progress)
            audit.run_started(self.run_id, self.task.name, self.mode, asdict(self.settings) | {"prompts": self.curator.prompt_versions()},
                              self.login, git_commit(self.root))
            try:
                pull_request = self._curate_and_settle(items, audit)
            except BaseException as error:
                # Whatever stops the run (a bug, Dagster terminating it, ^C), what it did so far is still recorded.
                self.failed = f"{type(error).__name__}: {error}"
                raise
            finally:
                summary = self.summary()
                audit.run_ended(self.run_id, self.stopped or self.failed, summary["outcomes"], pull_request,
                                summary["usage"])
                self._keep_summary(summary, pull_request)
        return RunReport(self.run_id, self.results, self.stopped, pull_request, summary)

    def _curate_and_settle(self, items: list[Item], audit: AuditLog) -> str | None:
        self._curate(items)
        accepted = [result for result in self.results if result.outcome == "accepted"]
        try:
            return self._settle(accepted, audit) if accepted else None
        except (urllib.error.URLError, TimeoutError, ConnectionError, BranchError) as error:
            # The proposals are in the audit log, accepted; only checking them together, or publishing, failed.
            self.unpublished = f"{type(error).__name__}: {error}"
            self.on_progress(f"No pull request: {self.unpublished}")
            return None

    def _keep_summary(self, summary: dict, pull_request: str | None) -> None:
        # Every run's summary is kept beside the audit log; a pull request also carries it (branch.py).
        path = self.audit_dir / "runs" / f"{self.run_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary | {"pull_request": pull_request}, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")

    def _items(self, build_dir: Path) -> list[Item]:
        if self.settings.evaluate:
            return self._evaluation_items()
        current_graph(self.root, build_dir)  # the queue is only as current as the build
        self.library = Library(self.web, known_sources(self.root))
        self.task = self.task_class.open(self.root, self.library, build_dir=build_dir)
        queue = self.task.items(load_queue(build_dir))
        if self.settings.names:
            queue = named(self.task, queue, self.settings.names, self.on_progress)
        return queue[: self.settings.items]

    def _evaluation_items(self) -> list[Item]:
        # The answers are the task's; the task is opened once they are known, to leave them out.
        chosen = self.task_class.evaluation_set()
        if self.settings.names:
            wanted = {name.casefold() for name in self.settings.names}
            chosen = [(item, answer) for item, answer in chosen if item.name.casefold() in wanted]
            evaluated = {item.name.casefold() for item, _ in chosen}
            # A name the evaluation set doesn't have has no answer to score against: say so, so a typo can't quietly
            # shrink the run.
            self.not_evaluated = [name for name in self.settings.names if name.casefold() not in evaluated]
            if self.not_evaluated:
                self.on_progress(f"Not in the evaluation set, so left out: {', '.join(self.not_evaluated)}")
        chosen = chosen[: self.settings.items]
        self.answers = {item.name: answer for item, answer in chosen}
        # The person's decisions are left out of what's taken, and their sources out of the library, as if undecided:
        # the agents decide them again.
        leaving_out = frozenset(self.answers)
        self.library = Library(self.web, known_sources(self.root, leaving_out))
        self.task = self.task_class.open(self.root, self.library, leaving_out=leaving_out)
        return [item for item, _ in chosen]

    def _curate(self, items: list[Item]) -> None:
        for item in items:
            self.stopped = self.curator.over_limit()
            if self.stopped:
                break
            try:
                self.results.append(self.curator.curate(item))
            except UsageLimitReached as error:
                self.stopped = f"the plan's usage limit was reached: {error}"
                break
            except SourcesUnavailable as error:
                self.stopped = str(error)
                break
        if self.stopped:
            left = len(items) - len(self.results)
            self.on_progress(f"Stopped: {self.stopped}. {left} items stay in the queue.")

    def _settle(self, accepted: list[ItemResult], audit: AuditLog) -> str | None:
        """Check the accepted changes in a worktree with the rest of the repository, drop those whose cited work is
        wrong, and open a draft pull request with the rest. Returns its URL, if one was opened."""
        with tempfile.TemporaryDirectory(prefix="agents-") as scratch:
            build_dir = Path(scratch) / "build"
            with Worktree(self.root, f"agents/{self.run_id}", self.settings.base, Path(scratch) / "worktree") as worktree:
                passing = self._gate(worktree, build_dir, accepted, audit)
                if not passing or not self.opens_pull_request:
                    return None
                summary = self.summary()
                counted = _count(len(passing), self.task.noun)
                proposals = Proposals(
                    title=f"Agent proposals: {counted} (run {self.run_id})",
                    body=pull_request_body(summary, self.task),
                    commit=f"feat(data): agent proposals for {counted} (run {self.run_id})",
                    files=tuple(self.task.files([result.change for result in passing])),
                )
                url = publish(worktree, build_dir, self.run_id, summary, proposals, self.settings.gh_command)
                self.on_progress(f"Opened a draft pull request: {url}")
                return url

    def _gate(self, worktree: Worktree, build_dir: Path, accepted: list[ItemResult], audit: AuditLog) -> list[ItemResult]:
        passing = list(accepted)
        touched = self.task.files([result.change for result in accepted])
        while passing:
            worktree.restore(touched)
            self.task.write(worktree.root, [result.change for result in passing])
            self.on_progress(f"Checking {_count(len(passing), 'change')}: downloading what they need and building the "
                             "graph")
            try:
                checks = gate(worktree.root, build_dir, self.downloads)
            except BuildError as error:
                for result in passing:
                    self._reject(audit, result, f"the graph didn't build with the run's changes: {error}")
                return []
            failing = []
            for result in passing:
                found = work_check(self.task.citation(result.change), checks)
                result.checks.append(found)
                audit.check(self.run_id, result.item.name, result.attempts, found.name, found.passed, found.detail)
                if not found.passed:
                    failing.append(result)
                    self._reject(audit, result, f"its cited work wasn't found: {found.detail}")
            if not failing:
                return passing
            passing = [result for result in passing if result not in failing]
        return []

    def _reject(self, audit: AuditLog, result: ItemResult, reason: str) -> None:
        # The audit log is append-only: an item's later outcome row supersedes its earlier one.
        result.outcome, result.reason, result.change = "rejected", reason, None
        audit.outcome(self.run_id, result.item.name, result.outcome, reason, None)

    def summary(self) -> dict:
        outcomes: dict[str, int] = {}
        for result in self.results:
            outcomes[result.outcome] = outcomes.get(result.outcome, 0) + 1
        summary = {
            "run": self.run_id,
            "task": self.task_class.name,
            "mode": self.mode,
            "started_at": self.started_at,
            "finished_at": _now(),
            "models": {"proposer": self.settings.proposer_model, "reviewer": self.settings.reviewer_model},
            "efforts": {"proposer": self.settings.proposer_effort, "reviewer": self.settings.reviewer_effort},
            # What the aliases above meant on the day: the models the calls actually ran on.
            "model_ids": dict(self.curator.model_ids),
            "prompts": self.curator.prompt_versions(),
            "plan": self.login.get("plan"),
            "stopped_because": self.stopped,
            "not_published_because": self.unpublished,
            "failed_because": self.failed,
            "outcomes": outcomes,
            "usage": asdict(self.curator.usage),
            # What code read to find the sources: no model's usage, but OpenAlex's daily allowance (ADR 0047).
            "sources": {"openalex_searches": self.library.openalex_searches,
                        "openalex_failures": self.library.openalex_failures,
                        "pages_downloaded": len(self.library.pages),
                        # How the downloads answered (200, 403, unreachable…): why a source gave no passages.
                        "page_statuses": dict(Counter(page.status.split(":")[0] for page in self.library.pages.values()))},
            "items": [result.summary() for result in self.results],
        }
        if self.answers:
            summary["score"] = self.task.score(self.results, self.answers)
        if self.not_evaluated:
            summary["not_evaluated"] = self.not_evaluated
        return summary


def named(task: Task, queue: list[Item], names: tuple[str, ...], on_progress: Callable[[str], None]) -> list[Item]:
    """The items named, in the order named: as the queue lists them, or as the task builds them if it doesn't. A name
    the task has no item for is left out, and said so."""
    listed = {item.name.casefold(): item for item in queue}
    items = []
    for name in names:
        item = task.named(name, listed.get(name.casefold()))
        if item is None:
            on_progress(f"No such item, so left out: {name}")
        else:
            items.append(item)
    return items


def pull_request_body(summary: dict, task: Task) -> str:
    run_id, items = summary["run"], summary["items"]
    accepted = [item for item in items if item["outcome"] == "accepted"]
    files = ", ".join(f"`{path}`" for path in task.files([item["change"] for item in accepted]))
    lines = [
        f"Agent run `{run_id}` proposes {_count(len(accepted), task.noun)} in {files} ({task.adrs}). Each passed "
        "the mechanical checks and the reviewer agent. None is verified: every reference stays `unverified` until a "
        "person reads it.",
        "",
        "**This pull request is the review.** Merge it, edit it, or close it.",
        "",
        *task.table(accepted),
    ]
    if others := [item for item in items if item["outcome"] != "accepted"]:
        lines += ["", "Not proposed; they stay in the curation queue:", ""]
        lines += [f"- {cell(item['item'])}: {item['outcome']}: "
                  f"{cell((item['reason'] or '').splitlines()[0] if item['reason'] else '')}" for item in others]
    usage = summary["usage"]
    lines += [
        "",
        f"Models: proposer {_model(summary, 'proposer')}, reviewer {_model(summary, 'reviewer')}. Prompts: "
        f"`{summary['prompts']['proposer']}`, `{summary['prompts']['reviewer']}`. {usage['calls']} calls; code made "
        f"{summary['sources']['openalex_searches']} OpenAlex searches and downloaded "
        f"{summary['sources']['pages_downloaded']} pages. Plan usage: five-hour "
        f"{_share(usage['first_limits'].get('five_hour'))} → {_share(usage['limits'].get('five_hour'))}, weekly "
        f"{_share(usage['first_limits'].get('seven_day'))} → {_share(usage['limits'].get('seven_day'))}.",
        "",
        f"The run's summary is `data/agent_runs/{run_id}.json`; every call, check and outcome is in the audit log.",
        "",
        "🤖 Generated with [Claude Code](https://claude.com/claude-code)",
    ]
    return "\n".join(lines) + "\n"


def _model(summary: dict, role: str) -> str:
    ran, effort = summary.get("model_ids", {}).get(role), summary.get("efforts", {}).get(role)
    return f"`{summary['models'][role]}`" + (f" (`{ran}`)" if ran else "") + (f" at {effort} effort" if effort else "")


def _share(value: float | None) -> str:
    return "?" if value is None else f"{value:.0%}"


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
