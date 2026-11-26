"""The second agent task: finding a quotable source for routes whose references are all unverified (ADR 0049).

Most of these routes cite books no one can quote from the web. Agents can't verify a route (only a person who read the
work marks a reference `verified`), but they can put a passage in front of that person: "read a book" becomes "check
this sentence on this page". A proposal is one of two changes to the route's file:

- **a quote for a reference the route already cites**, when that work's own page (its URL, or the free copy OpenAlex
  lists for it) has a sentence supporting what the reference says it supports;
- **a new reference with a quote**, from another page the repository cites or an open-access work OpenAlex finds.

Code finds the passages: sentences that name what the route makes (or, for a route that does something, its tools or
technique) and something it takes. The proposer, with no tools, chooses one and says what it supports; code fills in
the rest from the passage and checks it, and a reviewer challenges it. The route stays in the queue either way, its
references unverified, until a person reads the quote.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
from capabilities.built import CHECKS_FILE, graph_dir
from capabilities.graph import Graph, load_documents, ore_crosswalk_rows

from .sources import Library, Passage, Source, Wanted
from .task import ChangeError, Check, Evidence, Finding, Prompt, Skip, Task, cell, offered, page_checks
from .web import excerpt
from . import yaml_edit

# OpenAlex searches built from a route: the archaeology of its process first, then experiments that redid it.
OPENALEX_SEARCHES = ("{label} archaeology", "{label} experimental archaeology")
ROLES = {"consumed": "uses up", "tool": "uses the tool", "action": "first does", "effect": "needs"}
SHORTEST_TERM = 3
SUPPORTS_LENGTH = 20


@dataclass(frozen=True)
class Route:
    """A curated route in the queue: its id (what the audit log calls it), label, file and document."""

    name: str
    detail: str
    path: Path  # relative to the repository
    document: dict = field(hash=False, compare=False)
    copies: tuple[str, ...] = ()  # the mining routes copied from it for each ore mineral (ADR 0045)


@dataclass(frozen=True)
class Terms:
    """What a passage about a route must name: its subject (what it makes, or its tools and technique) and something
    else it takes."""

    main: tuple[str, ...]
    others: tuple[str, ...]

    def wanted(self) -> Wanted:
        return Wanted(_pattern(self.main), _pattern(self.others), _pattern(self.main))


@dataclass(frozen=True)
class RouteProposal:
    decision: str
    reference: int | None = None  # the index of the route's reference the quote is for; None for a new reference
    citation: str = ""
    url: str = ""
    quote: str = ""
    supports: str = ""
    adds_url: bool = False  # the reference had no URL: the page the quote is on is added with it
    unsure_why: str = ""


def proposal_schema(passages: int) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["decision", "passage", "supports", "unsure_why"],
        "properties": {
            "decision": {"enum": ["propose", "unsure"]},
            "passage": {"enum": list(range(passages + 1))},
            "supports": {"type": "string"},
            "unsure_why": {"type": "string"},
        },
    }


class RouteSources(Task):
    """Routes whose references are all unverified: a quoted source for each, for a person to read."""

    name = "route_sources"
    run_prefix = "routes"
    adrs = "ADR 0035, ADR 0048, ADR 0049"
    noun = "route"
    prompts = ("route_proposer", "route_reviewer")
    review_about = ("quote", "supports", "citation", "source", "reference")

    def __init__(self, root: Path, graph: Graph, library: Library, free_copies: dict[str, str]):
        self.root, self.graph, self.library, self.free_copies = root, graph, library, free_copies
        self.paths = {document.data["id"]: document.path.relative_to(root) for document in load_documents(root)[0]
                      if document.data.get("kind") == "route"}
        self.copies: dict[str, list[str]] = {}
        for row in ore_crosswalk_rows(root):
            if row.get("mined_like") and row.get("id"):
                self.copies.setdefault(row["mined_like"], []).append(f"mine-{row['id']}")

    @classmethod
    def open(cls, root: Path, library: Library, build_dir: Path | None = None,
             leaving_out: frozenset[str] = frozenset()) -> RouteSources:
        return cls(root, Graph.from_curated(root), library, free_copies(build_dir) if build_dir else {})

    def items(self, queue: list[dict]) -> list[Route]:
        # The routes copied for each ore mineral aren't in a file: they follow the route they were copied from.
        return [route for item in queue if item["kind"] == "route_unverified"
                and (route := self.route(item["subject"])) is not None]

    def named(self, name: str, queued: Route | None) -> Route | None:
        return queued or self.route(name)

    def route(self, route_id: str) -> Route | None:
        if route_id not in self.graph.routes or route_id not in self.paths:
            return None
        document = self.graph.routes[route_id]
        return Route(route_id, document["label"], self.paths[route_id], document,
                     tuple(sorted(self.copies.get(route_id, []))))

    def terms(self, route: Route) -> Terms:
        document = route.document
        achieves = document["achieves"]
        techniques = [self.graph.label(t) for t in document.get("techniques", [])]
        needed = [requirement for requirement in document["requires"]
                  if requirement.get("thing") or requirement.get("category")]
        labels = {id_: self.graph.label(id_) for r in needed for id_ in (r.get("thing") or r.get("category"),)}
        if achieves.get("thing"):
            # The thing it makes; a technique ("Pottery", "Woodworking") is too broad to name the route by, so it
            # only counts as something else it speaks of (find-only run, 2026-11-25).
            main = [self.graph.label(achieves["thing"])]
            others = list(labels.values()) + techniques
        else:
            # A route that does something (cuts, moves, heats) is named by its tools and technique, not the verb.
            tools = [labels[r.get("thing") or r.get("category")] for r in needed if r["role"] == "tool"]
            main = [*tools, *techniques] or list(labels.values())
            others = [label for label in labels.values() if label not in tools] or tools
        activity = _activity(document["label"])
        return Terms(_terms(main), _terms(others) + ((activity,) if activity else ()))

    def own_sources(self, route: Route) -> dict[str, int]:
        """The pages of the route's own references, by URL, with each reference's index: its URL, else the free copy
        OpenAlex lists for the work (only for a confirmed match, `found`)."""
        pages = {}
        for index, reference in enumerate(route.document.get("references", [])):
            url = (reference.get("url") or "").strip()
            if not url.startswith(("http://", "https://")):
                url = self.free_copies.get(reference["citation"].strip(), "")
            if url and url not in pages:
                pages[url] = index
        return pages

    def find(self, route: Route) -> Finding | Skip:
        terms = self.terms(route)
        own = self.own_sources(route)
        references = route.document.get("references", [])
        first = tuple(Source(" ".join(references[i]["citation"].split()), url, "cited by this route")
                      for url, i in own.items())
        label = re.sub(r"\s*\([^)]*\)", "", route.document["label"])
        found = self.library.passages(terms.wanted(), [search.format(label=label) for search in OPENALEX_SEARCHES],
                                      first)
        detail = (f"terms: {', '.join(terms.main)} | {', '.join(terms.others)}; "
                  f"{len(own)} of its {len(references)} references can be read")
        if not found.passages:
            return Skip("passages_found", f"no source found says it: {found.detail()}; {detail}")
        return Finding(found, (Check("passages_found", True, f"{found.detail()}; {detail}"),), own)

    def proposer_task(self, prompt: Prompt, route: Route, finding: Finding, feedback: str | None) -> str:
        own, references = finding.about, route.document.get("references", [])
        return prompt.render(
            route=self.describe(route), references=_listed(references),
            passages="\n\n".join(offered(p, _cited_note(p, own, references)) for p in finding.passages),
            feedback=f"\nYour last proposal for this route was sent back:\n{feedback}" if feedback else "",
        )

    def proposal_schema(self, finding: Finding) -> dict:
        return proposal_schema(len(finding.passages))

    def proposal(self, output: dict, route: Route, finding: Finding) -> RouteProposal:
        text = lambda key: " ".join(str(output.get(key) or "").split())  # noqa: E731
        if text("decision") != "propose":
            return RouteProposal(text("decision") or "unsure", unsure_why=text("unsure_why"))
        passage = next(p for p in finding.passages if p.number == output["passage"])
        index = finding.about.get(passage.source.url)
        if index is None:
            return RouteProposal("propose", None, passage.source.citation, passage.source.url, passage.sentence,
                                 text("supports"))
        reference = route.document["references"][index]
        return RouteProposal("propose", index, reference["citation"], passage.source.url, passage.sentence,
                             reference.get("supports", ""), adds_url=not reference.get("url"))

    def check(self, route: Route, proposal: RouteProposal, finding: Finding) -> tuple[list[Check], Evidence]:
        references = route.document.get("references", [])
        if proposal.reference is None:
            cited = [r for r in references if r["citation"].strip().casefold() == proposal.citation.casefold()
                     or (r.get("url") and r["url"].strip() == proposal.url)]
            checks = [Check("citation_is_new", not cited, f"the route already cites it: {cited[0]['citation']}"
                            if cited else "the route doesn't cite this work yet")]
            long_enough = len(proposal.supports) >= SUPPORTS_LENGTH
            checks.append(Check("supports_is_said", long_enough, "says what it supports" if long_enough
                                else "a new reference must say what it supports, in a sentence"))
        else:
            reference = references[proposal.reference]
            quoted = bool(reference.get("quote"))
            checks = [Check("reference_has_no_quote", not quoted, f"reference {proposal.reference + 1} already has a "
                            "quote" if quoted else f"a quote for reference {proposal.reference + 1}")]
            # A person's verified or secondary reference keeps what they wrote: an unread quote under it would read as
            # theirs. A route named for a run needn't be in the queue, so it can have one.
            unverified = reference.get("status") == "unverified"
            checks.append(Check("reference_is_unverified", unverified, f"reference {proposal.reference + 1} is "
                                f"{reference.get('status')}, so a person has read it" if not unverified
                                else f"reference {proposal.reference + 1} is unverified"))
        on_page, page, found = page_checks(proposal.url, proposal.quote, self.library)
        named = bool(self.terms(route).wanted().named.search(proposal.quote))
        checks += on_page + [Check("quote_names_the_route", named, "the quote names what the route makes or uses"
                                   if named else "the quote doesn't name what the route makes, or its tools")]
        return checks, Evidence(page, excerpt(*found) if found else None)

    def reviewer_task(self, prompt: Prompt, route: Route, proposal: RouteProposal, evidence: Evidence) -> str:
        references = route.document.get("references", [])
        if proposal.reference is None:
            reference = "A new reference for this route."
        else:
            reference = (f"A quote for reference {proposal.reference + 1}, which the route already cites; the quote "
                         "must support what that reference says it supports.")
        page = evidence.page
        return prompt.render(
            route=self.describe(route), references=_listed(references), reference=reference,
            citation=proposal.citation, url=proposal.url, page_title=page.title if page and page.title else "none",
            quote=proposal.quote, supports=proposal.supports, excerpt=evidence.excerpt or "",
        )

    def describe(self, route: Route) -> str:
        """The route as a person reads it in the app: what it achieves, what it takes, and its notes."""
        document = route.document
        achieves = document["achieves"]
        goal = (self.graph.label(achieves["thing"]) if achieves.get("thing") else
                f"to {self.graph.label(achieves['verb']).lower()}" if achieves.get("verb") else
                achieves.get("effect", ""))
        lines = [f"{document['label']} ({route.name}): it makes or achieves {goal}."]
        if document.get("techniques"):
            lines.append("Technique: " + ", ".join(self.graph.label(t) for t in document["techniques"]) + ".")
        for requirement in document["requires"]:
            what = requirement.get("thing") or requirement.get("category") or requirement.get("verb") \
                or requirement.get("effect") or ""
            label = self.graph.label(what) if what in self.graph.things or what in self.graph.verbs else what
            conditions = "; ".join(f"{c['quantity']} {c['op']} {c.get('value', c.get('band'))}"
                                   for c in requirement.get("where", []))
            note = f" {requirement['notes']}" if requirement.get("notes") else ""
            lines.append(f"- It {ROLES.get(requirement['role'], requirement['role'])} {label}"
                         + (f" ({conditions})" if conditions else "") + f".{note}")
        if document.get("notes"):
            lines.append(f"Notes: {' '.join(document['notes'].split())}")
        return "\n".join(lines)

    def change(self, route: Route, proposal: RouteProposal, run_id: str) -> dict:
        """The reference added, or the fields added to one, with the route's file. Every reference stays unverified:
        passing the agents' review isn't reading the work (ADR 0035)."""
        change = {"route": route.name, "file": str(route.path), "reference": proposal.reference,
                  "citation": proposal.citation, "url": proposal.url, "supports": proposal.supports,
                  "quote": proposal.quote, "proposed_by": run_id, "copies": list(route.copies)}
        if proposal.reference is not None:
            change["adds_url"] = proposal.adds_url
        return change

    def files(self, changes: list[dict]) -> list[Path]:
        return sorted({Path(change["file"]) for change in changes})

    def write(self, root: Path, changes: list[dict]) -> None:
        for change in changes:
            path = root / change["file"]
            try:
                path.write_text(_edited(path.read_text(encoding="utf-8"), change), encoding="utf-8")
            except (yaml_edit.EditError, OSError) as error:
                raise ChangeError(change, f"{change['file']}: {error}") from error

    def citation(self, change: dict) -> str | None:
        return change["citation"].strip()

    def table(self, accepted: list[dict]) -> list[str]:
        lines = ["| Route | Reference | Source | Supports | Quote |", "|---|---|---|---|---|"]
        for item in accepted:
            change = item["change"]
            which = "new" if change["reference"] is None else f"quote for reference {change['reference'] + 1}"
            copies = f" (and its copies {', '.join(f'`{c}`' for c in change['copies'])})" if change["copies"] else ""
            lines.append(f"| `{change['route']}`{copies} | {which} | [{cell(change['citation'])}]({change['url']}) | "
                         f"{cell(change['supports'])} | {cell(change['quote'])} |")
        return lines


def _edited(text: str, change: dict) -> str:
    if change["reference"] is None:
        return yaml_edit.add_reference(text, {
            "citation": change["citation"], "url": change["url"], "supports": change["supports"],
            "quote": change["quote"], "status": "unverified", "proposed_by": change["proposed_by"]})
    # By its citation, not the number it had in the run's copy: the file written to is the base branch's, where the
    # references may be in another order.
    fields = {"url": change["url"]} if change.get("adds_url") else {}
    return yaml_edit.quote_reference(text, yaml_edit.reference_citing(text, change["citation"]), fields | {
        "quote": change["quote"], "proposed_by": change["proposed_by"]})


def free_copies(build_dir: Path) -> dict[str, str]:
    """The free copy OpenAlex lists for each cited work it matched (ADR 0047), by citation: only a confirmed match, as
    a possible one or a review of the work would put another work's words under this citation."""
    path = graph_dir(build_dir) / CHECKS_FILE
    if not path.is_file():
        return {}
    rows = duckdb.sql("select citation, free_copy from read_parquet(?) where result = 'found' and free_copy is not null",
                      params=[str(path)]).fetchall()
    return {citation.strip(): url for citation, url in rows}


def _terms(labels: list[str]) -> tuple[str, ...]:
    """The words to look for: each label, and a parenthesis that is a name of its own ("Bloom iron (wrought iron)")."""
    terms: list[str] = []
    for label in labels:
        outside = re.sub(r"\s*\([^)]*\)", "", label).strip().lower()
        inside = [p.strip().lower() for p in re.findall(r"\(([^)]*)\)", label) if len(p.split()) > 1]
        for term in (outside, *inside):
            if len(term) >= SHORTEST_TERM and term not in terms:
                terms.append(term)
    return tuple(terms)


# Verbs that say nothing of how a thing is made: "make" matched "does not make up" (find-only run, 2026-11-25).
GENERIC_ACTIVITIES = {"making", "building", "selecting", "gathering", "collecting"}


def _activity(label: str) -> str | None:
    """What the route does, from its label's first word ("Smelting copper ore" → smelting), to look for as a term."""
    first = label.split()[0].lower()
    return first if first.endswith("ing") and len(first) > 5 and first not in GENERIC_ACTIVITIES else None


def _pattern(terms: tuple[str, ...]) -> re.Pattern:
    """A term, its plural, and a verb's other forms ("smelted" for "smelting", "quarried" for "quarrying")."""
    return re.compile("|".join(_forms(term) for term in terms) or r"(?!)", re.IGNORECASE)


def _forms(term: str) -> str:
    if not term.endswith("ing"):
        return rf"\b{re.escape(term)}(?:e?s)?\b"
    stem = term[:-3]
    if re.search(r"[^aeiou]y$", stem):  # quarrying: quarry, quarries, quarried, quarrier
        return rf"\b{re.escape(stem[:-1])}(?:y|ying|ies|ied|ier|iers)\b"
    stem = re.sub(r"([^aeiou])\1$", r"\1", stem)  # knapping → knap, knapped, knapper
    # A verb's own endings, never any: "allo" found "allow", "cast" "castle" (code review, 2026-11-26).
    verb = rf"{re.escape(stem)}{re.escape(stem[-1])}?(?:e|es|ed|er|ers|ing)"
    if len(stem) < 4:
        return rf"\b{verb}\b"  # "min" alone, or "mins", would find something else
    # The stem alone (a smith, cast bronze) only in lower case: "Smith (1981)" is an author.
    return rf"\b(?:{verb}|(?-i:{re.escape(stem)}s?))\b"


def _listed(references: list[dict]) -> str:
    return "\n".join(f"{i}. {r['citation']} Supports: {r.get('supports') or 'not said'}. Status: {r['status']}."
                     for i, r in enumerate(references, start=1)) or "None."


def _cited_note(passage: Passage, own: dict[str, int], references: list[dict]) -> str:
    index = own.get(passage.source.url)
    if index is None:
        return ""
    return (f"\n(This is reference {index + 1}, which the route already cites for: "
            f"{references[index].get('supports') or 'nothing said'})")

