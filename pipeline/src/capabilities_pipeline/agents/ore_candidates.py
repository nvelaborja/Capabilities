"""The first agent task: reviewing ore candidates, the minerals MRDS lists on many copper, iron and tin deposits that
the ore crosswalk hasn't decided yet (ADR 0045, ADR 0048).

A proposal is a crosswalk row: the mineral's Wikidata item, its ore class (or none), and a source with the passage that
supports it. Code finds the item and the candidate passages (sources.py); the proposer, with no tools, chooses the class
and the passage that supports it, and says what it supports. Code fills in the rest (the quote, citation and URL from
the passage, the id, and the route it is mined like) and checks everything it can before a reviewer agent sees it. An
item with no Wikidata item, one already decided, or no passages, is skipped without asking a model anything.
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from capabilities.graph import ORE_CROSSWALK, Graph, ore_crosswalk_rows

from .sources import NETWORK_ERRORS, OPENALEX_SEARCHES, Library, Passage, Wanted
from .task import Check, Evidence, Finding, Prompt, Skip, Task, cell, offered, page_checks
from .web import WikidataItem, excerpt

EVALUATION = Path(__file__).parent / "evaluation" / "ore_candidates.csv"
# The crosswalk's classes, as its source test accepts them (pipeline/dbt/models/staging/_sources.yml).
ORE_CLASSES = ("copper-ore", "copper-sulphide-ore", "iron-ore", "tin-ore", "none")
NONE_MEANS = ("Not smelted for copper, iron or tin: an ore of another metal, a mineral that comes with the ore but isn't "
              "smelted, or one useless for smelting.")
# The crosswalk's columns, in order (data-format.md). An agent's row leaves status empty: unverified.
COLUMNS = ("id", "wikidata", "mrds_ore", "class", "mined_like", "citation", "url", "supports", "quote", "status",
           "proposed_by", "notes")


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
    def from_choice(cls, output: dict, item: WikidataItem, passages: list[Passage]) -> Proposal:
        """The proposer's choice made a proposal: the passage it chose gives the quote, citation and URL."""
        text = lambda key: " ".join(str(output.get(key) or "").split())  # noqa: E731
        if text("decision") != "propose":
            return cls(text("decision") or "unsure", unsure_why=text("unsure_why"))
        passage = next(p for p in passages if p.number == output["passage"])
        return cls("propose", item.id, text("class"), passage.source.citation, passage.source.url, passage.sentence,
                   text("supports"), text("notes"))


def proposal_schema(passages: int) -> dict:
    """The proposer's answer: a decision, and for a proposal, a class and the number of one of the passages offered (0
    for none, with "unsure")."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["decision", "class", "passage", "supports", "notes", "unsure_why"],
        "properties": {
            "decision": {"enum": ["propose", "unsure"]},
            "class": {"enum": [*ORE_CLASSES, ""]},
            "passage": {"enum": list(range(passages + 1))},
            "supports": {"type": "string"},
            "notes": {"type": "string"},
            "unsure_why": {"type": "string"},
        },
    }

@dataclass(frozen=True)
class Context:
    """What a proposal must fit: the classes and what each means, the route each class is mined like, and the ids and
    Wikidata items already taken."""

    classes: dict[str, str]
    templates: dict[str, str]
    taken_ids: frozenset[str]
    taken_items: frozenset[str]
    decided_items: frozenset[str] = frozenset()  # the ore crosswalk's own items: minerals already decided

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
            decided_items=frozenset(row["wikidata"] for row in kept),
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


def proposer_task(prompt: Prompt, candidate: Candidate, item: WikidataItem, passages: list[Passage], context: Context,
                  feedback: str | None) -> str:
    classes = "\n".join(f"- {name}: {meaning}" for name, meaning in context.classes.items())
    return prompt.render(
        name=candidate.name, detail=candidate.detail, wikidata=item.id, wikidata_label=item.label or "",
        wikidata_description=item.description or "no description", classes=classes,
        passages="\n\n".join(offered(passage) for passage in passages),
        feedback=f"\nYour last proposal for this mineral was sent back:\n{feedback}" if feedback else "",
    )


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


def check(candidate: Candidate, proposal: Proposal, context: Context, web: Library) -> tuple[list[Check], Evidence]:
    """Everything code can check about a proposal before an agent reviews it (ADR 0035): the class and the route it
    implies, the Wikidata item, the cited page, and the quote on it. Every check runs, so a proposal sent back hears all
    that is wrong with it at once."""
    checks = [_class_check(proposal, context)]
    try:
        item = web.wikidata_item(proposal.wikidata) if proposal.wikidata else None
    except NETWORK_ERRORS as error:
        # Wikidata is down, not the proposal wrong: say so, and let the proposer try again.
        item = None
        checks.append(Check("wikidata_item_is_the_mineral", False, f"Wikidata couldn't be reached: {error}"))
    else:
        checks += _item_checks(candidate, proposal, item, context)
    if proposal.ore_class != "none":
        taken = candidate.id in context.taken_ids
        checks.append(Check("id_is_new", not taken, f"{candidate.id!r} is already an id in the graph" if taken
                            else f"the mineral's id will be {candidate.id!r}"))
    on_page, page, found = page_checks(proposal.url, proposal.quote, web)
    checks += on_page + [_names_the_mineral(candidate, proposal, item)]
    return checks, Evidence(page, excerpt(*found) if found else None, item)


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


def _names_the_mineral(candidate: Candidate, proposal: Proposal, item: WikidataItem | None) -> Check:
    names = {candidate.name, *((item.label,) if item and item.label else ())}
    named = any(re.search(rf"\b{re.escape(name)}", proposal.quote, re.IGNORECASE) for name in names)
    return Check("quote_names_the_mineral", named, "the quote names the mineral" if named
                 else f"the quote doesn't name {candidate.name}")


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


def queue_candidates(queue: list[dict], count: int | None) -> list[Candidate]:
    """The first `count` ore candidates in the curation queue (all of them for None): the most widely listed first."""
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


def score(results: list, answers: dict[str, dict]) -> dict:
    """How the agents' answers compare with a person's: the class and Wikidata item proposed, and above all whether
    anything wrong was accepted, which is what the checks and the reviewer are there to stop."""
    tally = {"items": len(results), "proposed": 0, "right": 0, "accepted": 0, "accepted_right": 0, "accepted_wrong": 0}
    for result in results:
        if result.proposal is None or result.proposal.decision != "propose":
            continue
        expected = answers[result.item.name]
        right = (result.proposal.ore_class, result.proposal.wikidata) == (expected["class"], expected["wikidata"])
        tally["proposed"] += 1
        tally["right"] += right
        if result.outcome == "accepted":
            tally["accepted"] += 1
            tally["accepted_right" if right else "accepted_wrong"] += 1
    return tally


class OreCandidates(Task):
    """Ore candidates as an agent task: a crosswalk row per mineral."""

    name = "ore_candidates"
    run_prefix = "ore"
    adrs = "ADR 0035, ADR 0048"
    noun = "ore mineral"
    prompts = ("ore_proposer", "ore_reviewer")
    review_about = ("class", "wikidata", "citation", "quote", "supports", "source", "notes")

    def __init__(self, context: Context, library: Library):
        self.context, self.library = context, library

    @classmethod
    def open(cls, root: Path, library: Library, build_dir: Path | None = None,
             leaving_out: frozenset[str] = frozenset()) -> OreCandidates:
        return cls(Context.of(root, leaving_out=leaving_out), library)

    @classmethod
    def evaluation_set(cls) -> list[tuple[Candidate, dict]]:
        return evaluation_set()

    def score(self, results: list, answers: dict[str, dict]) -> dict:
        return score(results, answers)

    def items(self, queue: list[dict]) -> list[Candidate]:
        return queue_candidates(queue, None)

    def named(self, name: str, queued: Candidate | None) -> Candidate:
        # A mineral the queue doesn't list is run all the same: re-running one already decided is how a row is redone.
        return queued or Candidate(name, "Named for this run; the curation queue doesn't list it.")

    def find(self, candidate: Candidate) -> Finding | Skip:
        """The mineral's Wikidata item, then passages that name it and speak of ore or smelting."""
        try:
            lookup = self.library.item_for(candidate.name)
        except NETWORK_ERRORS as error:
            return Skip("wikidata_item_found", f"Wikidata couldn't be searched: {error}")
        item = lookup.item
        if item is None:
            return Skip("wikidata_item_found", f"no Wikidata item is called {candidate.name!r} and is a mineral. The "
                        "search found: " + ("; ".join(lookup.seen) or "nothing"))
        if item.id in self.context.decided_items:
            return Skip("wikidata_item_found",
                        f"{item.id} ({item.label}) is already decided: ore_minerals.csv has a row for it")
        if item.id in self.context.taken_items:
            # A curated thing's item (limonite): how MRDS's name maps onto that node is a person's call, not an agent's.
            return Skip("wikidata_item_found", f"{item.id} ({item.label}) is a curated thing's item "
                        "(wikidata_things.csv): a person decides how MRDS's name maps to it")
        names = {candidate.name, *((item.label,) if item.label else ())}
        found = self.library.passages(Wanted.mineral(names),
                                      [search.format(name=candidate.name) for search in OPENALEX_SEARCHES])
        # The hits are recorded on success too: what else was there is part of why this one was taken.
        item_found = Check("wikidata_item_found", True, f"{item.id} ({item.label}). The search found: "
                           + "; ".join(lookup.seen))
        if not found.passages:
            return Skip("passages_found", "no source found speaks of it as an ore: " + found.detail(), (item_found,))
        return Finding(found, (item_found, Check("passages_found", True, found.detail())), item)

    def proposer_task(self, prompt: Prompt, candidate: Candidate, finding: Finding, feedback: str | None) -> str:
        return proposer_task(prompt, candidate, finding.about, finding.passages, self.context, feedback)

    def proposal_schema(self, finding: Finding) -> dict:
        return proposal_schema(len(finding.passages))

    def proposal(self, output: dict, candidate: Candidate, finding: Finding) -> Proposal:
        return Proposal.from_choice(output, finding.about, finding.passages)

    def check(self, candidate: Candidate, proposal: Proposal, finding: Finding) -> tuple[list[Check], Evidence]:
        return check(candidate, proposal, self.context, self.library)

    def reviewer_task(self, prompt: Prompt, candidate: Candidate, proposal: Proposal, evidence: Evidence) -> str:
        return reviewer_task(prompt, candidate, proposal, evidence, self.context)

    def change(self, candidate: Candidate, proposal: Proposal, run_id: str) -> dict:
        return crosswalk_row(candidate, proposal, self.context, run_id)

    def files(self, changes: list[dict]) -> list[Path]:
        return [ORE_CROSSWALK]

    def write(self, root: Path, changes: list[dict]) -> None:
        write_crosswalk(root, changes)

    def citation(self, row: dict) -> str | None:
        # A row rejecting a mineral builds nothing, so its reference isn't looked up (ADR 0047). Its page and quote
        # were still checked, and the reviewer read them.
        return None if row["class"] == "none" else row["citation"].strip()

    def table(self, accepted: list[dict]) -> list[str]:
        lines = ["| Mineral | Class | Wikidata | Source | Quote |", "|---|---|---|---|---|"]
        for item in accepted:
            row = item["change"]
            lines.append(f"| {cell(item['item'])} | `{row['class']}` | [{row['wikidata']}](https://www.wikidata.org/"
                         f"wiki/{row['wikidata']}) | [{cell(row['citation'])}]({row['url']}) | {cell(row['quote'])} |")
        return lines
