"""One agent run over ore candidates: find, choose, check, challenge, and gather what passed for a pull request
(ADR 0035, ADR 0048).

Per item: code finds the mineral's Wikidata item and candidate passages from sources (sources.py); a proposer agent, with
no tools, chooses the class and the passage that supports it; code checks the proposal; a reviewer agent, with no tools
and none of the proposer's reasoning, challenges it with the page around the passage. A failed check or a "revise" sends
it back to the proposer with the reasons, a bounded number of times. An item with no item or no passages is skipped
without asking a model anything. Items run one at a time, and the run stops before the next item once the plan's usage
passes a threshold, or at once if the limit is reached: the item in progress is lost, and the rest stay in the queue.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Callable

from .audit import AuditLog
from .claude import EFFORTS, AgentError, Answer, ClaudeCode, UsageLimitReached
from .ore_candidates import (
    REVIEW_SCHEMA,
    Candidate,
    Check,
    Context,
    Prompt,
    Proposal,
    check,
    crosswalk_row,
    proposal_schema,
    proposer_task,
    reviewer_task,
)
from .sources import NETWORK_ERRORS, Found, Library
from .web import WikidataItem

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
    candidate: Candidate
    outcome: str  # accepted, rejected, sent_back (attempts used up), unsure, skipped (nothing to ask about), failed,
    # or found (a find-only run)
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

    def __init__(self, run_id: str, settings: Settings, context: Context, audit: AuditLog, library: Library,
                 on_progress: Callable[[str], None] = lambda message: None):
        self.run_id, self.settings, self.context, self.audit, self.library = run_id, settings, context, audit, library
        self.on_progress = on_progress
        self.proposer = ClaudeCode(settings.proposer_model, (), PROPOSER_TURNS, settings.claude_command,
                                   effort=settings.proposer_effort)
        self.reviewer = ClaudeCode(settings.reviewer_model, (), REVIEWER_TURNS, settings.claude_command,
                                   effort=settings.reviewer_effort)
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
        found = self._find(candidate)
        if isinstance(found, ItemResult):
            return self._finish(found)
        item, passages = found
        if self.settings.find_only:
            offered = "\n".join(f"[{p.number}] {p.source.citation}: {p.sentence}" for p in passages.passages)
            return self._finish(ItemResult(candidate, "found", f"{item.id}; {passages.detail()}\n{offered}", 0))
        feedback, last = None, None
        for attempt in range(1, self.settings.attempts + 1):
            try:
                last = self._attempt(candidate, item, passages, attempt, feedback)
            except UsageLimitReached:
                raise
            except AgentError as error:
                return self._finish(ItemResult(candidate, "failed", str(error), attempt))
            if last.outcome != "sent_back":
                return self._finish(last)
            feedback = last.reason
        return self._finish(last)

    def _find(self, candidate: Candidate) -> tuple[WikidataItem, Found] | ItemResult:
        """The item and the passages for a mineral, found in code; or why the item is skipped, with no model asked."""
        self.on_progress(f"{candidate.name}: finding its Wikidata item and sources")
        try:
            item = self.library.item_for(candidate.name)
        except NETWORK_ERRORS as error:
            return self._skipped(candidate, "wikidata_item_found", f"Wikidata couldn't be searched: {error}")
        if item is None:
            return self._skipped(candidate, "wikidata_item_found",
                                 f"no Wikidata item is called {candidate.name!r} and is a mineral species")
        if item.id in self.context.taken_items:
            return self._skipped(candidate, "wikidata_item_found", f"{item.id} is already in a crosswalk")
        found = self.library.passages(item, candidate.name)
        self.audit.check(self.run_id, candidate.name, 0, "wikidata_item_found", True, f"{item.id} ({item.label})")
        if not found.passages:
            return self._skipped(candidate, "passages_found", "no source found speaks of it as an ore: " + found.detail())
        self.audit.check(self.run_id, candidate.name, 0, "passages_found", True, found.detail())
        return item, found

    def _skipped(self, candidate: Candidate, check_name: str, reason: str) -> ItemResult:
        self.audit.check(self.run_id, candidate.name, 0, check_name, False, reason)
        return ItemResult(candidate, "skipped", reason, 0)

    def _attempt(self, candidate: Candidate, item: WikidataItem, found: Found, attempt: int,
                 feedback: str | None) -> ItemResult:
        passages = found.passages
        task = proposer_task(self.proposer_prompt, candidate, item, passages, self.context, feedback)
        answer = self._ask("proposer", candidate, attempt, self.proposer, self.proposer_prompt, task,
                           proposal_schema(len(passages)))
        if answer.output.get("decision") == "propose" and not answer.output.get("passage"):
            return ItemResult(candidate, "sent_back", "It proposed a class without choosing a passage.", attempt)
        proposal = Proposal.from_choice(answer.output, item, passages)
        if proposal.decision != "propose":
            return ItemResult(candidate, "unsure", proposal.unsure_why or "the proposer couldn't decide", attempt, proposal)
        checks, evidence = check(candidate, proposal, self.context, self.library)
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
            # A failed call still used the plan (Tenorite's 30 turns used about 14 points of the five-hour window), so
            # what it spent is counted and recorded, and the next threshold check sees the plan's usage after it.
            spent = error.spent
            self.audit.call(self.run_id, candidate.name, attempt, role, prompt.version,
                            claude.settings() | {"model_id": spent.model if spent else None}, task, spent,
                            error=f"{type(error).__name__}: {error}")
            if spent:
                self.usage.add(spent)
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
