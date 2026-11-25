"""One agent run over ore candidates: propose, check, challenge, and gather what passed for a pull request (ADR 0035,
ADR 0048).

Per item: a proposer agent researches the mineral and proposes a crosswalk row; code checks it; a reviewer agent, with
no tools and none of the proposer's reasoning, challenges it with the pages the pipeline downloaded. A failed check or
a "revise" sends it back to the proposer with the reasons, a bounded number of times. Items run one at a time, and the
run stops before the next item once the plan's usage passes a threshold, or at once if the limit is reached: the item
in progress is lost, and the rest stay in the queue.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Callable

from .audit import AuditLog
from .claude import AgentError, Answer, ClaudeCode, UsageLimitReached
from .ore_candidates import (
    PROPOSAL_SCHEMA,
    REVIEW_SCHEMA,
    Candidate,
    Check,
    Context,
    Prompt,
    Proposal,
    check,
    crosswalk_row,
    proposer_task,
    reviewer_task,
)
from .web import Web

# The proposer searches and reads; each search or page is a turn.
PROPOSER_TURNS = 30
# The reviewer only answers: one turn for the answer, one for the structured output.
REVIEWER_TURNS = 3


@dataclass(frozen=True)
class Settings:
    items: int = 5
    evaluate: bool = False
    proposer_model: str = "opus"
    reviewer_model: str = "opus"
    attempts: int = 2  # proposals per item: the first, and one more after being sent back
    # Stop before the next item once this share of the plan's five-hour or weekly usage is used.
    stop_at_five_hour: float = 0.8
    stop_at_seven_day: float = 0.9
    pull_request: bool = True
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
        if self.items < 1 or self.attempts < 1:
            raise ValueError("a run needs at least one item, and each item at least one attempt")


@dataclass
class ItemResult:
    candidate: Candidate
    outcome: str  # accepted, rejected, sent_back (attempts used up), unsure, failed
    reason: str
    attempts: int = 0
    proposal: Proposal | None = None
    row: dict | None = None
    checks: list[Check] = field(default_factory=list)
    review: dict | None = None

    def summary(self) -> dict:
        return {
            "mineral": self.candidate.name,
            "outcome": self.outcome,
            "reason": self.reason,
            "attempts": self.attempts,
            "row": self.row,
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
    """Works through ore candidates for one run, recording everything in the audit log."""

    def __init__(self, run_id: str, settings: Settings, context: Context, audit: AuditLog, web: Web,
                 on_progress: Callable[[str], None] = lambda message: None):
        self.run_id, self.settings, self.context, self.audit, self.web = run_id, settings, context, audit, web
        self.on_progress = on_progress
        self.proposer = ClaudeCode(settings.proposer_model, ("WebSearch", "WebFetch"), PROPOSER_TURNS,
                                   settings.claude_command)
        self.reviewer = ClaudeCode(settings.reviewer_model, (), REVIEWER_TURNS, settings.claude_command)
        self.proposer_prompt = Prompt.load("ore_proposer")
        self.reviewer_prompt = Prompt.load("ore_reviewer")
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

    def curate(self, candidate: Candidate) -> ItemResult:
        """One item, to an outcome. A usage limit reached mid-item is raised: the run stops there."""
        feedback, last = None, None
        for attempt in range(1, self.settings.attempts + 1):
            try:
                last = self._attempt(candidate, attempt, feedback)
            except UsageLimitReached:
                raise
            except AgentError as error:
                return self._finish(ItemResult(candidate, "failed", str(error), attempt))
            if last.outcome != "sent_back":
                return self._finish(last)
            feedback = last.reason
        return self._finish(last)

    def _attempt(self, candidate: Candidate, attempt: int, feedback: str | None) -> ItemResult:
        task = proposer_task(self.proposer_prompt, candidate, self.context, feedback)
        answer = self._ask("proposer", candidate, attempt, self.proposer, self.proposer_prompt, task, PROPOSAL_SCHEMA)
        proposal = Proposal.from_output(answer.output)
        if proposal.decision != "propose":
            return ItemResult(candidate, "unsure", proposal.unsure_why or "the proposer couldn't decide", attempt, proposal)
        checks, evidence = check(candidate, proposal, self.context, self.web)
        for c in checks:
            self.audit.check(self.run_id, candidate.name, attempt, c.name, c.passed, c.detail)
        failed = [c for c in checks if not c.passed]
        if failed:
            reason = "It failed these checks:\n" + "\n".join(f"- {c.name}: {c.detail}" for c in failed)
            return ItemResult(candidate, "sent_back", reason, attempt, proposal, checks=checks)
        task = reviewer_task(self.reviewer_prompt, candidate, proposal, evidence, self.context)
        review = self._ask("reviewer", candidate, attempt, self.reviewer, self.reviewer_prompt, task, REVIEW_SCHEMA).output
        objections = "\n".join(f"- {o['about']}: {o['objection']}" for o in review.get("objections") or [])
        if review["verdict"] == "accept":
            row = crosswalk_row(candidate, proposal, self.context, self.run_id)
            return ItemResult(candidate, "accepted", review.get("summary", ""), attempt, proposal, row, checks, review)
        if review["verdict"] == "reject":
            return ItemResult(candidate, "rejected", f"{review.get('summary', '')}\n{objections}".strip(), attempt,
                              proposal, checks=checks, review=review)
        return ItemResult(candidate, "sent_back", "The reviewer asked for changes:\n" + objections, attempt, proposal,
                          checks=checks, review=review)

    def _ask(self, role: str, candidate: Candidate, attempt: int, claude: ClaudeCode, prompt: Prompt, task: str,
             schema: dict) -> Answer:
        self.on_progress(f"{candidate.name}: asking the {role} (attempt {attempt})")
        try:
            answer = claude.ask(task, prompt.system, schema)
        except AgentError as error:
            self.audit.call(self.run_id, candidate.name, attempt, role, prompt.version, claude.settings(), task,
                            error=f"{type(error).__name__}: {error}")
            raise
        self.audit.call(self.run_id, candidate.name, attempt, role, prompt.version,
                        claude.settings() | {"model_id": answer.model}, task, answer)
        self.usage.add(answer)
        if answer.model:
            self.model_ids[role] = answer.model
        return answer

    def _finish(self, result: ItemResult) -> ItemResult:
        self.audit.outcome(self.run_id, result.candidate.name, result.outcome, result.reason, result.row)
        self.on_progress(f"{result.candidate.name}: {result.outcome}")
        return result


def new_run_id(now: datetime | None = None) -> str:
    return "ore-" + (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
