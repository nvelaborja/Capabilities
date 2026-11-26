"""One agent run over a task's items: find, choose, check, challenge, and gather what passed for a pull request
(ADR 0035, ADR 0048, ADR 0049).

Per item: code finds candidate passages from sources (the task, with sources.py); a proposer agent, with no tools,
chooses the passage that supports a claim; code checks the proposal; a reviewer agent, with no tools and none of the
proposer's reasoning, challenges it with the page around the passage. A failed check or a "revise" sends it back to the
proposer with the reasons, a bounded number of times. An item code finds nothing for is skipped without asking a model
anything. Items run one at a time, and the run stops before the next item once the plan's usage
passes a threshold, or at once if the limit is reached: the item in progress is lost, and the rest stay in the queue.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Callable

from .audit import AuditLog
from .claude import EFFORTS, AgentError, Answer, ClaudeCode, UsageLimitReached
from .task import Check, Evidence, Finding, Item, Prompt, Skip, Task, review_schema

# Neither role has tools: one turn for the answer, one for the structured output, and one to spare.
PROPOSER_TURNS = 3
REVIEWER_TURNS = 3


@dataclass(frozen=True)
class Settings:
    items: int = 5
    evaluate: bool = False
    # The proposer only chooses among passages code found: Sonnet at medium effort. The reviewer, the last check before
    # a person, thinks harder: Sonnet at high effort, which caught as much as Opus for under half the cost (ADR 0048,
    # Evaluation).
    proposer_model: str = "sonnet"
    reviewer_model: str = "sonnet"
    # How hard each role thinks (claude.EFFORTS); None is Claude Code's default for the model.
    proposer_effort: str | None = "medium"
    reviewer_effort: str | None = "high"
    attempts: int = 2  # proposals per item: the first, and one more after being sent back
    # Stop before the next item once this share of the plan's five-hour or weekly usage is used.
    stop_at_five_hour: float = 0.8
    stop_at_seven_day: float = 0.9
    pull_request: bool = True
    task: str = "ore_candidates"  # TASKS in run.py: ore_candidates (ADR 0048) or route_sources (ADR 0049)
    # Run these items, in this order, instead of the top of the queue: minerals by MRDS name, routes by id. For
    # re-running chosen items, and for tests that mustn't depend on what the queue holds.
    names: tuple[str, ...] = ()
    # Find the items and passages, record them, and ask no model: what a run would offer, for nothing of the plan.
    find_only: bool = False
    base: str = "origin/main"  # what the proposals' branch starts from
    claude_command: str = "claude"
    gh_command: str = "gh"

    def __post_init__(self):
        # A threshold is a share, 0 to 1, as Claude Code reports usage: 80 for 80% would never be reached, and the run
        # would go on until the plan's limit locks its owner out.
        for name in ("stop_at_five_hour", "stop_at_seven_day"):
            if not 0 < getattr(self, name) <= 1:
                raise ValueError(f"{name} is a share of the plan's usage, above 0 and at most 1 (0.8 for 80%), "
                                 f"not {getattr(self, name)}")
        for name in ("proposer_effort", "reviewer_effort"):
            if getattr(self, name) not in (None, *EFFORTS):
                raise ValueError(f"{name} is one of {', '.join(EFFORTS)}, or unset, not {getattr(self, name)!r}")
        if self.items < 1 or self.attempts < 1:
            raise ValueError("a run needs at least one item, and each item at least one attempt")


@dataclass
class ItemResult:
    item: Item
    outcome: str  # accepted, rejected, sent_back (attempts used up), unsure, skipped (nothing to ask about), failed,
    # or found (a find-only run)
    reason: str
    attempts: int = 0
    proposal: object | None = None
    change: dict | None = None  # what an accepted proposal changes in the repository's data
    checks: list[Check] = field(default_factory=list)
    review: dict | None = None

    def summary(self) -> dict:
        return {
            "item": self.item.name,
            "outcome": self.outcome,
            "reason": self.reason,
            "attempts": self.attempts,
            "change": self.change,
            "checks": [asdict(c) for c in self.checks],
            "review": self.review,
        }


@dataclass
class Usage:
    """What a run used: calls, tokens, the API-equivalent cost Claude Code reports, and the plan's usage seen."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    web_searches: int = 0
    web_fetches: int = 0
    api_equivalent_usd: float = 0.0
    first_limits: dict = field(default_factory=dict)
    limits: dict = field(default_factory=dict)

    def add(self, answer: Answer) -> None:
        self.calls += 1
        self.input_tokens += answer.usage.get("input_tokens") or 0
        self.output_tokens += answer.usage.get("output_tokens") or 0
        self.cache_read_tokens += answer.usage.get("cache_read_input_tokens") or 0
        self.cache_creation_tokens += answer.usage.get("cache_creation_input_tokens") or 0
        self.web_searches += sum(call["name"] == "WebSearch" for call in answer.tool_calls)
        self.web_fetches += sum(call["name"] == "WebFetch" for call in answer.tool_calls)
        self.api_equivalent_usd += answer.cost_usd or 0.0
        if answer.limits:
            self.first_limits = self.first_limits or dict(answer.limits)
            self.limits = dict(answer.limits)


class Curator:
    """Works through a task's items for one run, recording everything in the audit log."""

    def __init__(self, run_id: str, settings: Settings, task: Task, audit: AuditLog,
                 on_progress: Callable[[str], None] = lambda message: None):
        self.run_id, self.settings, self.task, self.audit = run_id, settings, task, audit
        self.on_progress = on_progress
        self.proposer = ClaudeCode(settings.proposer_model, (), PROPOSER_TURNS, settings.claude_command,
                                   effort=settings.proposer_effort)
        self.reviewer = ClaudeCode(settings.reviewer_model, (), REVIEWER_TURNS, settings.claude_command,
                                   effort=settings.reviewer_effort)
        proposer, reviewer = task.prompts
        self.proposer_prompt = Prompt.load(proposer)
        self.reviewer_prompt = Prompt.load(reviewer)
        self.review_schema = review_schema(task.review_about)
        self.usage = Usage()
        self.model_ids: dict[str, str] = {}  # the model each role last ran on, as Claude Code reported it

    def prompt_versions(self) -> dict:
        return {"proposer": self.proposer_prompt.version, "reviewer": self.reviewer_prompt.version}

    def over_limit(self) -> str | None:
        """Why the run should stop before the next item, if the plan's usage seen so far says it should."""
        thresholds = {"five_hour": self.settings.stop_at_five_hour, "seven_day": self.settings.stop_at_seven_day}
        for window, threshold in thresholds.items():
            used = self.usage.limits.get(window)
            if used is not None and used >= threshold:
                return f"the plan's {window.replace('_', '-')} usage reached {used:.0%} (the run stops at {threshold:.0%})"
        return None

    def curate(self, item: Item) -> ItemResult:
        """One item, to an outcome. A usage limit reached mid-item is raised: the run stops there."""
        self.on_progress(f"{item.name}: finding sources")
        finding = self.task.find(item)
        if isinstance(finding, Skip):
            for passed in finding.passed:
                self._record(item, 0, passed)
            self._record(item, 0, Check(finding.check, False, finding.reason))
            return self._finish(ItemResult(item, "skipped", finding.reason, 0))
        for passed in finding.checks:
            self._record(item, 0, passed)
        if self.settings.find_only:
            offered = "\n".join(f"[{p.number}] {p.source.citation}: {p.sentence}" for p in finding.passages)
            return self._finish(ItemResult(item, "found", f"{finding.found.detail()}\n{offered}", 0))
        feedback, objected, last = None, None, None
        for attempt in range(1, self.settings.attempts + 1):
            try:
                last = self._attempt(item, finding, attempt, feedback, objected)
            except UsageLimitReached:
                raise
            except AgentError as error:
                return self._finish(ItemResult(item, "failed", str(error), attempt))
            if last.outcome != "sent_back":
                return self._finish(last)
            feedback = last.reason
            objected = _objections(last.review) if last.review else objected
        return self._finish(last)

    def _record(self, item: Item, attempt: int, check: Check) -> None:
        self.audit.check(self.run_id, item.name, attempt, check.name, check.passed, check.detail)

    def _attempt(self, item: Item, finding: Finding, attempt: int, feedback: str | None,
                 objected: str | None) -> ItemResult:
        task = self.task.proposer_task(self.proposer_prompt, item, finding, feedback)
        answer = self._ask("proposer", item, attempt, self.proposer, self.proposer_prompt, task,
                           self.task.proposal_schema(finding))
        if answer.output.get("decision") == "propose" and not answer.output.get("passage"):
            return ItemResult(item, "sent_back", "It proposed without choosing a passage.", attempt)
        proposal = self.task.proposal(answer.output, item, finding)
        if proposal.decision != "propose":
            return ItemResult(item, "unsure", proposal.unsure_why or "the proposer couldn't decide", attempt, proposal)
        checks, evidence = self.task.check(item, proposal, finding)
        for c in checks:
            self._record(item, attempt, c)
        failed = [c for c in checks if not c.passed]
        if failed:
            reason = "It failed these checks:\n" + "\n".join(f"- {c.name}: {c.detail}" for c in failed)
            return ItemResult(item, "sent_back", reason, attempt, proposal, checks=checks)
        review = self.review(item, attempt, proposal, evidence, objected)
        objections = _objections(review)
        if review["verdict"] == "accept":
            change = self.task.change(item, proposal, self.run_id)
            return ItemResult(item, "accepted", review.get("summary", ""), attempt, proposal, change, checks, review)
        if review["verdict"] == "reject":
            return ItemResult(item, "rejected", f"{review.get('summary', '')}\n{objections}".strip(), attempt,
                              proposal, checks=checks, review=review)
        return ItemResult(item, "sent_back", "The reviewer asked for changes:\n" + objections, attempt, proposal,
                          checks=checks, review=review)

    def review(self, item: Item, attempt: int, proposal: object, evidence: Evidence, objected: str | None = None) -> dict:
        """The reviewer's verdict on a proposal (accept, revise or reject, with objections), recorded in the audit log.
        A re-check of a merged fact asks it too (recheck.py)."""
        task = self.task.reviewer_task(self.reviewer_prompt, item, proposal, evidence)
        if objected:
            # Without them a second review starts afresh, and finds new, finer faults in a proposal that fixed the
            # first ones: copper-from-ore took the reviewer's own wording and was sent back for its scope (run
            # routes-20261126-191441).
            task += f"\n\nYou reviewed this item's last proposal and asked for these changes:\n{objected}\n"
        return self._ask("reviewer", item, attempt, self.reviewer, self.reviewer_prompt, task, self.review_schema).output

    def _ask(self, role: str, item: Item, attempt: int, claude: ClaudeCode, prompt: Prompt, task: str,
             schema: dict) -> Answer:
        self.on_progress(f"{item.name}: asking the {role} (attempt {attempt})")
        try:
            answer = claude.ask(task, prompt.system, schema)
        except AgentError as error:
            # A failed call still used the plan (Tenorite's 30 turns used about 14 points of the five-hour window), so
            # what it spent is counted and recorded, and the next threshold check sees the plan's usage after it.
            spent = error.spent
            self.audit.call(self.run_id, item.name, attempt, role, prompt.version,
                            claude.settings() | {"model_id": spent.model if spent else None}, task, spent,
                            error=f"{type(error).__name__}: {error}")
            if spent:
                self.usage.add(spent)
            raise
        self.audit.call(self.run_id, item.name, attempt, role, prompt.version,
                        claude.settings() | {"model_id": answer.model}, task, answer)
        self.usage.add(answer)
        if answer.model:
            self.model_ids[role] = answer.model
        return answer

    def _finish(self, result: ItemResult) -> ItemResult:
        self.audit.outcome(self.run_id, result.item.name, result.outcome, result.reason, result.change)
        self.on_progress(f"{result.item.name}: {result.outcome}")
        return result


def new_run_id(prefix: str, now: datetime | None = None) -> str:
    return f"{prefix}-" + (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")


def _objections(review: dict) -> str:
    return "\n".join(f"- {o['about']}: {o['objection']}" for o in review.get("objections") or [])
