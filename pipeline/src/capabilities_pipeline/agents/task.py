"""What every agent task shares, and what each one supplies (ADR 0048, ADR 0049).

A run (run.py) and the curator (curate.py) are the same for every task: items one at a time, code finding the passages,
a proposer choosing one, code checking it, a reviewer challenging it, the plan's usage watched, everything in the audit
log, and what was accepted checked together and opened as a draft pull request. A task supplies the rest: which items,
what a passage must say, the prompts, what a proposal is and how it is checked, and the files it changes.
"""

from __future__ import annotations

import hashlib
import re
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any, Protocol

from .sources import Found, Library, Passage
from .web import Page, locate

PROMPTS = Path(__file__).parent / "prompts"
QUOTE_LENGTH = (40, 1000)
# Sources whose data the project may not use (CREDITS.md): Mindat's terms forbid it.
EXCLUDED_SITES = ("mindat.org",)


class Item(Protocol):
    """One thing a task decides: what the audit log and progress call it, and why it is in the queue."""

    name: str
    detail: str


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class Skip:
    """Why an item isn't put to a model: the check that failed, what it found, and the checks that passed before it."""

    check: str
    reason: str
    passed: tuple[Check, ...] = ()


@dataclass(frozen=True)
class Finding:
    """What code found for an item: the passages, the checks finding them passed, and what else the task looked up."""

    found: Found
    checks: tuple[Check, ...]
    about: Any = None  # an ore candidate's Wikidata item; a route's own references

    @property
    def passages(self) -> list[Passage]:
        return self.found.passages


@dataclass(frozen=True)
class Evidence:
    """What the pipeline downloaded to check a proposal, which the reviewer reads instead of the proposer's account."""

    page: Page | None = None
    excerpt: str | None = None
    item: Any = None  # anything else the task looked up (an ore candidate's Wikidata item)


@dataclass(frozen=True)
class Prompt:
    """A prompt file: the system prompt, then `---task---` and the task, a template filled in for each item."""

    system: str
    task: Template
    version: str  # the file's hash: what the audit log records, so results can be compared across prompt changes

    @classmethod
    def load(cls, name: str) -> Prompt:
        text = (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
        system, marker, task = text.partition("\n---task---\n")
        if not marker or not task.strip():
            # Without it the agent would get its role and an empty task, and answer nothing in particular.
            raise ValueError(f"the prompt {name} has no task: it needs a line '---task---' and the task after it")
        return cls(system.strip(), Template(task.strip()), hashlib.sha256(text.encode()).hexdigest()[:12])

    def render(self, **values) -> str:
        return self.task.substitute(**values).strip()


def review_schema(about: tuple[str, ...]) -> dict:
    """The reviewer's answer: a verdict, objections each about one part of the proposal, and a summary."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["verdict", "objections", "summary"],
        "properties": {
            "verdict": {"enum": ["accept", "revise", "reject"]},
            "objections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["about", "objection"],
                    "properties": {"about": {"enum": list(about)}, "objection": {"type": "string"}},
                },
            },
            "summary": {"type": "string"},
        },
    }


class Task(ABC):
    """One kind of agent work. Built for a run with the run's library (`open` in each task's module)."""

    name: str  # how the audit log and summaries name the task
    run_prefix: str  # a run's id starts with it
    adrs: str  # the decisions it follows, as the pull request names them
    noun: str  # what one accepted proposal is, counted in the pull request's title
    prompts: tuple[str, str]  # the proposer's and the reviewer's prompt files
    review_about: tuple[str, ...]  # what the reviewer's objections can be about

    library: Library

    @classmethod
    def evaluation_set(cls) -> list[tuple[Item, dict]]:
        """Items a person already decided, with what they decided; a task without one can't be evaluated."""
        raise ValueError(f"{cls.name} has no evaluation set: run it, and review its pull request instead")

    def score(self, results: list, answers: dict[str, dict]) -> dict:
        return {}

    @abstractmethod
    def items(self, queue: list[dict]) -> list[Item]:
        """The task's items in the curation queue, in the queue's order."""

    @abstractmethod
    def named(self, name: str, queued: Item | None) -> Item | None:
        """An item named for a run: the queue's, or one built for it; None if there is no such item."""

    @abstractmethod
    def find(self, item: Item) -> Finding | Skip:
        """The passages for an item, found in code; or why no model is asked about it."""

    @abstractmethod
    def proposer_task(self, prompt: Prompt, item: Item, finding: Finding, feedback: str | None) -> str: ...

    @abstractmethod
    def proposal_schema(self, finding: Finding) -> dict: ...

    @abstractmethod
    def proposal(self, output: dict, item: Item, finding: Finding) -> Any:
        """The proposer's choice as a proposal, with `decision` and `unsure_why`; the passage gives the quote."""

    @abstractmethod
    def check(self, item: Item, proposal: Any, finding: Finding) -> tuple[list[Check], Evidence]:
        """Everything code can check before the reviewer sees it. Every check runs, so a proposal sent back hears all
        that is wrong with it at once."""

    @abstractmethod
    def reviewer_task(self, prompt: Prompt, item: Item, proposal: Any, evidence: Evidence) -> str: ...

    @abstractmethod
    def change(self, item: Item, proposal: Any, run_id: str) -> dict:
        """The accepted proposal as the change it makes to the repository's data, recorded in the audit log."""

    @abstractmethod
    def files(self, changes: list[dict]) -> list[Path]:
        """The files the changes write, relative to the repository: restored between gate passes, and committed."""

    @abstractmethod
    def write(self, root: Path, changes: list[dict]) -> None: ...

    @abstractmethod
    def citation(self, change: dict) -> str | None:
        """The work the change cites, to find among the build's citation checks; None if it isn't looked up."""

    @abstractmethod
    def table(self, accepted: list[dict]) -> list[str]:
        """The pull request's table of accepted proposals (each a run summary's item), in Markdown."""


def offered(passage: Passage, note: str = "") -> str:
    """A passage as the proposer reads it: its number and source, then the sentence in «guillemets» with the sentences
    either side."""
    context = " ".join(part for part in (passage.before, f"«{passage.sentence}»", passage.after) if part)
    return (f"[{passage.number}] From: {passage.source.citation} ({passage.source.origin}; {passage.source.url}){note}\n"
            f"{context}")


def excluded_site(url: str) -> str | None:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return next((site for site in EXCLUDED_SITES if host == site or host.endswith("." + site)), None)


def page_checks(url: str, quote: str, library: Library) -> tuple[list[Check], Page | None, tuple[str, int] | None]:
    """The checks on the cited page: that its site may be cited, that it loads, and that the quote is on it word for
    word. Returns them with the page and where the quote was found."""
    excluded = excluded_site(url)
    checks = [Check("source_may_be_used", not excluded,
                    f"{excluded} may not be cited: its data may not be used" if excluded else "the site may be cited")]
    page = library.page(url) if url and not excluded else None
    checks.append(Check("cited_page_loads", bool(page and page.loaded), _page_detail(page, url)))
    found = locate(quote, page.text) if page and page.loaded else None
    shortest, longest = QUOTE_LENGTH
    if not shortest <= len(quote) <= longest:
        checks.append(Check("quote_is_on_the_page", False,
                            f"the quote is {len(quote)} characters; it must be {shortest} to {longest}"))
    elif found:
        checks.append(Check("quote_is_on_the_page", True, f"found word for word in the {page.kind} page"))
    else:
        checks.append(Check("quote_is_on_the_page", False, "not found word for word on the page" if page and page.loaded
                            else "the page couldn't be read, so the quote couldn't be checked"))
    return checks, page, found


def _page_detail(page: Page | None, url: str) -> str:
    if not url:
        return "no URL given"
    if page is None:
        return "not fetched"
    if page.loaded:
        return f"{page.status}, {page.kind}, {len(page.text)} characters of text"
    return f"{page.status}, no text" if page.status == "200" else page.status


def cell(text: str) -> str:
    """Text from a page or an agent, made safe for one table cell: on one line, and with a word joiner after every @, so
    that a quote saying "@someone" doesn't notify a GitHub user of that name when the pull request opens."""
    return " ".join(text.split()).replace("|", "\\|").replace("@", "@⁠")
