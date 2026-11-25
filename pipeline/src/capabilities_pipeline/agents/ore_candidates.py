"""The first agent task: reviewing ore candidates, the minerals MRDS lists on many copper, iron and tin deposits that
the ore crosswalk hasn't decided yet (ADR 0045, ADR 0048).

A proposal is a crosswalk row: the mineral's Wikidata item, its ore class (or none), and a source with the passage that
supports it. The agent decides those; code fills in the rest (the id, and the route it is mined like, from the rows
already in the crosswalk) and checks everything it can before a reviewer agent sees it.
"""

from __future__ import annotations

import csv
import hashlib
import http.client
import re
import urllib.error
import urllib.parse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from string import Template

from capabilities.graph import ORE_CROSSWALK, Graph, ore_crosswalk_rows

from .web import Page, Web, WikidataItem, excerpt, locate

PROMPTS = Path(__file__).parent / "prompts"
EVALUATION = Path(__file__).parent / "evaluation" / "ore_candidates.csv"
# The crosswalk's classes, as its source test accepts them (pipeline/dbt/models/staging/_sources.yml).
ORE_CLASSES = ("copper-ore", "copper-sulphide-ore", "iron-ore", "tin-ore", "none")
NONE_MEANS = ("Not smelted for copper, iron or tin: an ore of another metal, a mineral that comes with the ore but isn't "
              "smelted, or one useless for smelting.")
# The crosswalk's columns, in order (data-format.md). An agent's row leaves status empty: unverified.
COLUMNS = ("id", "wikidata", "mrds_ore", "class", "mined_like", "citation", "url", "supports", "quote", "status",
           "proposed_by", "notes")
QUOTE_LENGTH = (40, 1000)
# Sources whose data the project may not use (CREDITS.md): Mindat's terms forbid it.
EXCLUDED_SITES = ("mindat.org",)


@dataclass(frozen=True)
class Candidate:
    """A mineral to decide: MRDS's name for it, and why it is in the queue."""

    name: str
    detail: str = ""

    @property
    def id(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-")


@dataclass(frozen=True)
class Proposal:
    decision: str
    wikidata: str = ""
    ore_class: str = ""
    citation: str = ""
    url: str = ""
    quote: str = ""
    supports: str = ""
    notes: str = ""
    unsure_why: str = ""

    @classmethod
    def from_output(cls, output: dict) -> Proposal:
        text = lambda key: " ".join(str(output.get(key) or "").split())  # noqa: E731
        return cls(text("decision"), text("wikidata").upper(), text("class"), text("citation"), text("url"),
                   str(output.get("quote") or "").strip(), text("supports"), text("notes"), text("unsure_why"))


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class Evidence:
    """What the pipeline downloaded to check a proposal, which the reviewer reads instead of the proposer's account."""

    item: WikidataItem | None = None
    page: Page | None = None
    excerpt: str | None = None


PROPOSAL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["decision", "wikidata", "class", "citation", "url", "quote", "supports", "notes", "unsure_why"],
    "properties": {
        "decision": {"enum": ["propose", "unsure"]},
        "wikidata": {"type": "string"},
        "class": {"enum": [*ORE_CLASSES, ""]},
        "citation": {"type": "string"},
        "url": {"type": "string"},
        "quote": {"type": "string"},
        "supports": {"type": "string"},
        "notes": {"type": "string"},
        "unsure_why": {"type": "string"},
    },
}

REVIEW_SCHEMA = {
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
                "properties": {
                    "about": {"enum": ["class", "wikidata", "citation", "quote", "supports", "source", "notes"]},
                    "objection": {"type": "string"},
                },
            },
        },
        "summary": {"type": "string"},
    },
}


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


@dataclass(frozen=True)
class Context:
    """What a proposal must fit: the classes and what each means, the route each class is mined like, and the ids and
    Wikidata items already taken."""

    classes: dict[str, str]
    templates: dict[str, str]
    taken_ids: frozenset[str]
    taken_items: frozenset[str]

    @classmethod
    def of(cls, root: Path, leaving_out: frozenset[str] = frozenset()) -> Context:
        """The repository's context. `leaving_out` names minerals (by MRDS name) to treat as undecided: an evaluation
        asks the agents again about rows a person already decided."""
        graph = Graph.from_curated(root)
        rows = tuple(ore_crosswalk_rows(root))
        kept = [row for row in rows if row["mrds_ore"].casefold() not in {n.casefold() for n in leaving_out}]
        classes = {name: _class_meaning(graph, name) for name in ORE_CLASSES}
        # The route most rows of a class are mined like: a new mineral of that class is mined the same way.
        templates = {}
        for name in ORE_CLASSES:
            uses = Counter(row["mined_like"] for row in rows if row["class"] == name and row["mined_like"])
            if uses:
                templates[name] = uses.most_common(1)[0][0]
        return cls(
            classes=classes,
            templates=templates,
            taken_ids=frozenset(graph.things) | frozenset(graph.routes) | {row["id"] for row in kept if row["id"]},
            taken_items=frozenset(row["wikidata"] for row in kept) | frozenset(_wikidata_things(root)),
        )


def _class_meaning(graph: Graph, name: str) -> str:
    if name == "none":
        return NONE_MEANS
    meaning = (graph.things.get(name) or {}).get("description", "").strip()
    if name == "copper-ore":
        meaning += " A copper mineral that carries sulphur belongs in copper-sulphide-ore instead."
    return meaning


def _wikidata_things(root: Path) -> list[str]:
    path = root / "data" / "crosswalks" / "wikidata_things.csv"
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as file:
        return [row["wikidata"].strip() for row in csv.DictReader(file) if row.get("wikidata", "").strip()]


def proposer_task(prompt: Prompt, candidate: Candidate, context: Context, feedback: str | None) -> str:
    classes = "\n".join(f"- {name}: {meaning}" for name, meaning in context.classes.items())
    return prompt.render(name=candidate.name, detail=candidate.detail, classes=classes,
                         feedback=f"\nYour last proposal for this mineral was sent back:\n{feedback}" if feedback else "")


def reviewer_task(prompt: Prompt, candidate: Candidate, proposal: Proposal, evidence: Evidence, context: Context) -> str:
    item, page = evidence.item, evidence.page
    return prompt.render(
        name=candidate.name, detail=candidate.detail,
        ore_class=proposal.ore_class, class_description=context.classes.get(proposal.ore_class, ""),
        wikidata=proposal.wikidata, wikidata_label=item.label if item else "", wikidata_description=item.description
        if item and item.description else "no description",
        citation=proposal.citation, url=proposal.url, page_title=page.title if page and page.title else "none",
        quote=proposal.quote, supports=proposal.supports, notes=proposal.notes, excerpt=evidence.excerpt or "",
    )


def check(candidate: Candidate, proposal: Proposal, context: Context, web: Web) -> tuple[list[Check], Evidence]:
    """Everything code can check about a proposal before an agent reviews it (ADR 0035): the class and the route it
    implies, the Wikidata item, the cited page, and the quote on it. Every check runs, so a proposal sent back hears all
    that is wrong with it at once."""
    checks = [_class_check(proposal, context)]
    try:
        item = web.wikidata_item(proposal.wikidata) if proposal.wikidata else None
    except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException, ValueError) as error:
        # Wikidata is down, not the proposal wrong: say so, and let the proposer try again.
        item = None
        checks.append(Check("wikidata_item_is_the_mineral", False, f"Wikidata couldn't be reached: {error}"))
    else:
        checks += _item_checks(candidate, proposal, item, context)
    if proposal.ore_class != "none":
        taken = candidate.id in context.taken_ids
        checks.append(Check("id_is_new", not taken, f"{candidate.id!r} is already an id in the graph" if taken
                            else f"the mineral's id will be {candidate.id!r}"))
    excluded = _excluded_site(proposal.url)
    checks.append(Check("source_may_be_used", not excluded,
                        f"{excluded} may not be cited: its data may not be used" if excluded else "the site may be cited"))
    page = web.page(proposal.url) if proposal.url and not excluded else None
    checks.append(Check("cited_page_loads", bool(page and page.loaded), _page_detail(page, proposal.url)))
    found = locate(proposal.quote, page.text) if page and page.loaded else None
    checks += _quote_checks(candidate, proposal, item, found, page)
    return checks, Evidence(item, page, excerpt(*found) if found else None)


def _class_check(proposal: Proposal, context: Context) -> Check:
    if proposal.ore_class not in context.classes:
        return Check("class_is_known", False, f"{proposal.ore_class!r} isn't one of {', '.join(context.classes)}")
    if proposal.ore_class != "none" and proposal.ore_class not in context.templates:
        return Check("class_is_known", False, f"no mineral of {proposal.ore_class} is in the crosswalk yet, so there is "
                     "no route to mine it like: a person must add the first one")
    mined = f", mined like {context.templates[proposal.ore_class]}" if proposal.ore_class != "none" else ""
    return Check("class_is_known", True, f"{proposal.ore_class}{mined}")


def _item_checks(candidate: Candidate, proposal: Proposal, item: WikidataItem | None, context: Context) -> list[Check]:
    if item is None:
        return [Check("wikidata_item_is_the_mineral", False, f"{proposal.wikidata or 'no item'} isn't a Wikidata item")]
    if item.id != proposal.wikidata:
        return [Check("wikidata_item_is_the_mineral", False, f"{proposal.wikidata} was merged into {item.id}: use that")]
    named = item.is_called(candidate.name)
    checks = [Check("wikidata_item_is_the_mineral", named,
                    f"{item.id} is {item.label!r} ({item.description or 'no description'})" + (
                        "" if named else f", and neither its label nor an alias is {candidate.name!r}"))]
    taken = item.id in context.taken_items
    checks.append(Check("wikidata_item_is_new", not taken, f"{item.id} is already in a crosswalk" if taken
                        else f"{item.id} isn't in a crosswalk yet"))
    return checks


def _quote_checks(candidate: Candidate, proposal: Proposal, item: WikidataItem | None,
                  found: tuple[str, int] | None, page: Page | None) -> list[Check]:
    shortest, longest = QUOTE_LENGTH
    if not shortest <= len(proposal.quote) <= longest:
        on_page = Check("quote_is_on_the_page", False,
                        f"the quote is {len(proposal.quote)} characters; it must be {shortest} to {longest}")
    elif found:
        on_page = Check("quote_is_on_the_page", True, f"found word for word in the {page.kind} page")
    else:
        on_page = Check("quote_is_on_the_page", False, "not found word for word on the page" if page and page.loaded
                        else "the page couldn't be read, so the quote couldn't be checked")
    names = {candidate.name, *((item.label,) if item and item.label else ())}
    named = any(re.search(rf"\b{re.escape(name)}", proposal.quote, re.IGNORECASE) for name in names)
    return [on_page, Check("quote_names_the_mineral", named, "the quote names the mineral" if named
                           else f"the quote doesn't name {candidate.name}")]


def _excluded_site(url: str) -> str | None:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return next((site for site in EXCLUDED_SITES if host == site or host.endswith("." + site)), None)


def _page_detail(page: Page | None, url: str) -> str:
    if not url:
        return "no URL given"
    if page is None:
        return "not fetched"
    if page.loaded:
        return f"{page.status}, {page.kind}, {len(page.text)} characters of text"
    return f"{page.status}, no text" if page.status == "200" else page.status


def crosswalk_row(candidate: Candidate, proposal: Proposal, context: Context, run_id: str) -> dict:
    """The proposal as a row of the ore crosswalk. Its reference is unverified (status left empty): passing the agents'
    review isn't reading the work (ADR 0035)."""
    rejected = proposal.ore_class == "none"
    return {
        "id": "" if rejected else candidate.id,
        "wikidata": proposal.wikidata,
        "mrds_ore": candidate.name,
        "class": proposal.ore_class,
        "mined_like": "" if rejected else context.templates[proposal.ore_class],
        "citation": proposal.citation,
        "url": proposal.url,
        "supports": proposal.supports,
        "quote": proposal.quote,
        "status": "",
        "proposed_by": run_id,
        "notes": proposal.notes,
    }


def evaluation_set() -> list[tuple[Candidate, dict]]:
    """The minerals a person already decided, with what they decided: what an evaluation asks the agents again."""
    with EVALUATION.open(newline="", encoding="utf-8") as file:
        return [(Candidate(row["mrds_ore"], row["detail"]), row) for row in csv.DictReader(file)]


def queue_candidates(queue: list[dict], count: int) -> list[Candidate]:
    """The first `count` ore candidates in the curation queue: the most widely listed first."""
    candidates = [item for item in queue if item["kind"] == "ore_candidate"]
    return [Candidate(item["label"], item["detail"].split(". Review it")[0] + ".") for item in candidates[:count]]


def write_crosswalk(root: Path, rows: list[dict]) -> None:
    """The crosswalk with the given rows in it: each replaces the row for the same mineral, or is added at the end."""
    path = root / ORE_CROSSWALK
    by_name = {row["mrds_ore"].casefold(): row for row in rows}
    with path.open(newline="", encoding="utf-8") as file:
        existing = list(csv.DictReader(file))
    kept = [by_name.pop(row["mrds_ore"].casefold(), row) for row in existing]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows([{column: row.get(column) or "" for column in COLUMNS} for row in kept + list(by_name.values())])
