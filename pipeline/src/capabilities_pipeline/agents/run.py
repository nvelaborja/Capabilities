"""Running agents over ore candidates, start to finish: what the Dagster job `agent_curation` calls (ADR 0048).

1. Check, before anything is spent, that Claude Code is on the user's Claude login (and `gh` logged in, if the run is
   to open a pull request).
2. Take the first items: from the curation queue, or, for an evaluation, the minerals a person already decided.
3. Work through them one at a time (curate.py), stopping before the plan's usage limits.
4. Check the accepted rows in a temporary worktree, and open a draft pull request with those that pass (branch.py). An
   evaluation opens none: it scores the agents' answers against the person's.
5. Record the run's end in the audit log, and write its summary.
"""

from __future__ import annotations

import json
import tempfile
import urllib.error
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from capabilities.built import current_graph, load_queue

from ..build import BuildError, git_commit
from .audit import AUDIT_FILE, AuditLog, audit_dir_for
from .branch import BranchError, Downloads, Worktree, check_gh, gate, publish, work_check
from .claude import UsageLimitReached, check_login
from .curate import Curator, ItemResult, Settings, new_run_id
from .ore_candidates import Candidate, Context, evaluation_set, queue_candidates, write_crosswalk
from .web import Web

TASK = "ore_candidates"


@dataclass
class RunReport:
    run_id: str
    results: list[ItemResult]
    stopped_because: str | None
    pull_request: str | None
    summary: dict = field(repr=False, default_factory=dict)


def run_ore_candidates(root: Path, build_dir: Path, settings: Settings, downloads: Downloads = Downloads(),
                       web: Web = Web(), on_progress: Callable[[str], None] = print,
                       audit_dir: Path | None = None) -> RunReport:
    """One run. The audit log and run summaries go in `audit_dir`, by default audit/ in the repository."""
    return Run(root, settings, downloads, web, on_progress, audit_dir or audit_dir_for(root)).execute(build_dir)


class Run:
    def __init__(self, root: Path, settings: Settings, downloads: Downloads, web: Web,
                 on_progress: Callable[[str], None], audit_dir: Path):
        self.root, self.settings, self.downloads, self.web, self.on_progress = root, settings, downloads, web, on_progress
        self.audit_dir = audit_dir
        self.run_id = new_run_id()
        self.mode = "evaluate" if settings.evaluate else "propose"
        self.started_at = _now()
        self.results: list[ItemResult] = []
        self.stopped: str | None = None
        self.unpublished: str | None = None  # why accepted rows weren't checked together or published, if they weren't
        self.answers: dict[str, dict] = {}

    @property
    def opens_pull_request(self) -> bool:
        return self.settings.pull_request and not self.settings.evaluate

    def execute(self, build_dir: Path) -> RunReport:
        self.login = check_login(self.settings.claude_command)
        if self.opens_pull_request:
            check_gh(self.settings.gh_command)
        candidates, context = self._items(build_dir)
        with AuditLog(self.audit_dir / AUDIT_FILE) as audit:
            self.curator = Curator(self.run_id, self.settings, context, audit, self.web, self.on_progress)
            audit.run_started(self.run_id, TASK, self.mode, asdict(self.settings) | {"prompts": self.curator.prompt_versions()},
                              self.login, git_commit(self.root))
            self._curate(candidates)
            accepted = [result for result in self.results if result.outcome == "accepted"]
            pull_request = None
            try:
                pull_request = self._settle(accepted, audit) if accepted else None
            except (urllib.error.URLError, TimeoutError, ConnectionError, BranchError) as error:
                # The proposals are in the audit log, accepted; only checking them together, or publishing, failed.
                self.unpublished = f"{type(error).__name__}: {error}"
                self.on_progress(f"No pull request: {self.unpublished}")
            summary = self.summary()
            audit.run_ended(self.run_id, self.stopped, summary["outcomes"], pull_request, summary["usage"])
        # Every run's summary is kept beside the audit log; a pull request also carries it (branch.py).
        path = self.audit_dir / "runs" / f"{self.run_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary | {"pull_request": pull_request}, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
        return RunReport(self.run_id, self.results, self.stopped, pull_request, summary)

    def _items(self, build_dir: Path) -> tuple[list[Candidate], Context]:
        if self.settings.evaluate:
            chosen = evaluation_set()[: self.settings.items]
            self.answers = {candidate.name: answer for candidate, answer in chosen}
            # The person's rows are left out of what's taken, as if undecided: the agents decide them again.
            return [candidate for candidate, _ in chosen], Context.of(self.root, leaving_out=frozenset(self.answers))
        current_graph(self.root, build_dir)  # the queue is only as current as the build
        return queue_candidates(load_queue(build_dir), self.settings.items), Context.of(self.root)

    def _curate(self, candidates: list[Candidate]) -> None:
        for candidate in candidates:
            self.stopped = self.curator.over_limit()
            if self.stopped:
                break
            try:
                self.results.append(self.curator.curate(candidate))
            except UsageLimitReached as error:
                self.stopped = f"the plan's usage limit was reached: {error}"
                break
        if self.stopped:
            left = len(candidates) - len(self.results)
            self.on_progress(f"Stopped: {self.stopped}. {left} items stay in the queue.")

    def _settle(self, accepted: list[ItemResult], audit: AuditLog) -> str | None:
        """Check the accepted rows in a worktree with the rest of the repository, drop those whose cited work isn't
        found, and open a draft pull request with the rest. Returns its URL, if one was opened."""
        with tempfile.TemporaryDirectory(prefix="agents-") as scratch:
            build_dir = Path(scratch) / "build"
            with Worktree(self.root, f"agents/{self.run_id}", self.settings.base, Path(scratch) / "worktree") as worktree:
                passing = self._gate(worktree, build_dir, accepted, audit)
                if not passing or not self.opens_pull_request:
                    return None
                summary = self.summary()
                title = f"Agent proposals: {_count(len(passing), 'ore mineral')} (run {self.run_id})"
                url = publish(worktree, build_dir, self.run_id, summary, title, pull_request_body(summary),
                              self.settings.gh_command)
                self.on_progress(f"Opened a draft pull request: {url}")
                return url

    def _gate(self, worktree: Worktree, build_dir: Path, accepted: list[ItemResult], audit: AuditLog) -> list[ItemResult]:
        passing = list(accepted)
        while passing:
            worktree.restore_crosswalk()
            write_crosswalk(worktree.root, [result.row for result in passing])
            self.on_progress(f"Checking {_count(len(passing), 'row')}: downloading what they need and building the graph")
            try:
                checks = gate(worktree.root, build_dir, self.downloads)
            except BuildError as error:
                for result in passing:
                    self._reject(audit, result, f"the graph didn't build with the run's rows: {error}")
                return []
            failing = []
            for result in passing:
                found = work_check(result.row, checks)
                result.checks.append(found)
                audit.check(self.run_id, result.candidate.name, result.attempts, found.name, found.passed, found.detail)
                if not found.passed:
                    failing.append(result)
                    self._reject(audit, result, f"its cited work wasn't found: {found.detail}")
            if not failing:
                return passing
            passing = [result for result in passing if result not in failing]
        return []

    def _reject(self, audit: AuditLog, result: ItemResult, reason: str) -> None:
        # The audit log is append-only: an item's later outcome row supersedes its earlier one.
        result.outcome, result.reason, result.row = "rejected", reason, None
        audit.outcome(self.run_id, result.candidate.name, result.outcome, reason, None)

    def summary(self) -> dict:
        outcomes: dict[str, int] = {}
        for result in self.results:
            outcomes[result.outcome] = outcomes.get(result.outcome, 0) + 1
        summary = {
            "run": self.run_id,
            "task": TASK,
            "mode": self.mode,
            "started_at": self.started_at,
            "finished_at": _now(),
            "models": {"proposer": self.settings.proposer_model, "reviewer": self.settings.reviewer_model},
            "prompts": self.curator.prompt_versions(),
            "plan": self.login.get("plan"),
            "stopped_because": self.stopped,
            "not_published_because": self.unpublished,
            "outcomes": outcomes,
            "usage": asdict(self.curator.usage),
            "items": [result.summary() for result in self.results],
        }
        if self.answers:
            summary["score"] = score(self.results, self.answers)
        return summary


def score(results: list[ItemResult], answers: dict[str, dict]) -> dict:
    """How the agents' answers compare with a person's: the class and Wikidata item proposed, and above all whether
    anything wrong was accepted, which is what the checks and the reviewer are there to stop."""
    tally = {"items": len(results), "proposed": 0, "right": 0, "accepted": 0, "accepted_right": 0, "accepted_wrong": 0}
    for result in results:
        if result.proposal is None or result.proposal.decision != "propose":
            continue
        expected = answers[result.candidate.name]
        right = (result.proposal.ore_class, result.proposal.wikidata) == (expected["class"], expected["wikidata"])
        tally["proposed"] += 1
        tally["right"] += right
        if result.outcome == "accepted":
            tally["accepted"] += 1
            tally["accepted_right" if right else "accepted_wrong"] += 1
    return tally


def pull_request_body(summary: dict) -> str:
    run_id, items = summary["run"], summary["items"]
    accepted = [item for item in items if item["outcome"] == "accepted"]
    lines = [
        f"Agent run `{run_id}` proposes {_count(len(accepted), 'row')} for `data/crosswalks/ore_minerals.csv` "
        "(ADR 0035, ADR 0048). Each passed the mechanical checks and the reviewer agent. None is verified: every "
        "reference stays `unverified` until a person reads it.",
        "",
        "**This pull request is the review.** Merge it, edit it, or close it.",
        "",
        "| Mineral | Class | Wikidata | Source | Quote |",
        "|---|---|---|---|---|",
    ]
    for item in accepted:
        row = item["row"]
        lines.append(f"| {item['mineral']} | `{row['class']}` | [{row['wikidata']}](https://www.wikidata.org/wiki/"
                     f"{row['wikidata']}) | [{_cell(row['citation'])}]({row['url']}) | {_cell(row['quote'])} |")
    if others := [item for item in items if item["outcome"] != "accepted"]:
        lines += ["", "Not proposed; they stay in the curation queue:", ""]
        lines += [f"- {item['mineral']}: {item['outcome']}: {_cell((item['reason'] or '').splitlines()[0] if item['reason'] else '')}"
                  for item in others]
    usage = summary["usage"]
    lines += [
        "",
        f"Models: proposer `{summary['models']['proposer']}`, reviewer `{summary['models']['reviewer']}`. Prompts: "
        f"`{summary['prompts']['proposer']}`, `{summary['prompts']['reviewer']}`. {usage['calls']} calls, "
        f"{usage['web_searches']} searches, {usage['web_fetches']} pages fetched. Plan usage: five-hour "
        f"{_share(usage['first_limits'].get('five_hour'))} → {_share(usage['limits'].get('five_hour'))}, weekly "
        f"{_share(usage['first_limits'].get('seven_day'))} → {_share(usage['limits'].get('seven_day'))}.",
        "",
        f"The run's summary is `data/agent_runs/{run_id}.json`; every call, check and outcome is in the audit log.",
        "",
        "🤖 Generated with [Claude Code](https://claude.com/claude-code)",
    ]
    return "\n".join(lines) + "\n"


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _share(value: float | None) -> str:
    return "?" if value is None else f"{value:.0%}"


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
