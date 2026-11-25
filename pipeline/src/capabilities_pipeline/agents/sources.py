"""Finding a mineral's Wikidata item and the passages that might say how it was used, in code (ADR 0048).

A model is asked only to judge: which class the passages support, and which passage says so. Everything else is found
and read here, the same way every time:

- **The item**: Wikidata's search for the mineral's name, keeping the item called exactly that (label or alias) that is
  an instance of *mineral species*.
- **The sources**: first the pages the repository already cites (its crosswalk rows and the curated layer's
  references), then open-access works OpenAlex finds for the mineral and smelting. Each page is downloaded once a run.
- **The passages**: the sentences of a source that name the mineral and speak of ore, smelting, roasting or a metal,
  word for word as the page has them, with the sentence before and after for context.

The quote, the citation and the URL of a proposal come from here, not from a model: a quote can't be a paraphrase, and
a citation can't be invented.
"""

from __future__ import annotations

import http.client
import re
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path

from capabilities.graph import load_documents, ore_crosswalk_rows

from ..citations import _references_in
from .web import MINERAL_SPECIES, Page, Web, WikidataItem

# Sentences worth a model's attention name the mineral and one of these.
SUBJECT = re.compile(r"\b(smelt\w*|ores?|roast\w*|furnaces?|slags?|bloom\w*|copper|iron|tin|metal\w*|min(e|ed|ing)|"
                     r"reduc\w*|sulph\w*|sulf\w*|flux\w*)\b", re.IGNORECASE)
# What ranks a sentence higher: smelting itself, and the past (the graph is about doing it by hand, ADR 0032).
SMELTING = re.compile(r"\b(smelt\w*|roast\w*|bloomer\w*|crucibles?|furnaces?)\b", re.IGNORECASE)
PAST = re.compile(r"\b(ancient|prehistor\w*|bronze age|iron age|chalcolithic|neolithic|roman|medieval|antiquity|"
                  r"archaeo\w*|early|historic\w*|BC|BCE)\b", re.IGNORECASE)
# What isn't a sentence of prose: a link, a DOI, a header or footer, a reference, a keyword list.
NOT_PROSE = re.compile(r"https?://|doi|\bvol\b|©|keywords?:|isbn|issn|\d+\s*[–-]\s*\d+\s*$", re.IGNORECASE)
# A reference-list entry starts with a surname and initials ("Smith J, Jones K (2001) …"); a sentence that cites a work
# in passing ("… (Tylecote et al. 1971) …") is still prose.
REFERENCE_ENTRY = re.compile(r"^[A-Z][\w'’-]+ [A-Z]{1,3}[,(]|^[A-Z][\w'’-]+, (?:[A-Z]\. ?){1,3}[,(]")
# A figure's or table's caption describes a picture, not what happened: never the evidence (Bornite, 2026-11-25).
CAPTION = re.compile(r"^\W*(fig(ure)?|table|plate|pl)\.?\s*[\dIVXivx]+\b", re.IGNORECASE)
# A caption's label alone, which a full stop splits from its text ("Table IV." then the caption's text).
CAPTION_LABEL = re.compile(r"^\W*(fig(ure)?|table|plate|pl)\.?\s*[\dIVXivx]+[a-z]?[.:]?$", re.IGNORECASE)
SENTENCE_END = re.compile(r"(?<=[.!?])[\"”’)]?\s+(?=[\"“‘(]?[A-Z0-9])")
# A full stop that ends an abbreviation or an initial, not a sentence: "(Fig. 2)", "Tylecote et al. 1971", "J. Smith".
# Splitting there cut accepted quotes off mid-sentence (Chalcopyrite and Siderite, 2026-11-25).
ABBREVIATION = re.compile(r"(\b(figs?|et al|e\.g|i\.e|cf|ca|approx|nos?|vols?|pp?|eds?|pls?|tabs?|sect|ch|esp|resp|vs|"
                          r"incl|dr|prof|st|mt)|\(c)\.$", re.IGNORECASE)
INITIAL = re.compile(r"(^|[\s(])[A-Z]\.$")
SENTENCE_LENGTH = (40, 1000)  # what a quote may be (ore_candidates.QUOTE_LENGTH)
# Archaeometallurgy first: a plain "smelting" finds mostly today's industry, and "ore" its mineral processing.
OPENALEX_SEARCHES = ("{name} archaeometallurgy", "{name} ancient smelting")
# Works that aren't a source for a claim: corrections, data deposits, front matter.
NOT_SOURCES = {"erratum", "dataset", "paratext", "editorial", "retraction", "peer-review", "letter", "other"}
OPENALEX_WORKS = 5  # per search
PASSAGES_PER_SOURCE = 3
PASSAGES = 12
# Names for the Wikidata classes a lookup reports, where we know them; others are shown by id.
CLASS_NAMES = {MINERAL_SPECIES: "mineral species", "Q11344": "chemical element"}
NETWORK_ERRORS = (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException, ValueError)


class SourcesUnavailable(Exception):
    """OpenAlex refuses searches (its daily allowance is spent, 429): every item after this one would find nothing,
    and look as if nothing speaks of it. The run stops instead, and the rest stay in the queue."""


@dataclass(frozen=True)
class Source:
    citation: str
    url: str
    origin: str  # "cited in the repository" or "OpenAlex"


@dataclass(frozen=True)
class Passage:
    number: int
    source: Source
    sentence: str  # word for word from the page: the quote, if it is chosen
    before: str = ""
    after: str = ""


@dataclass(frozen=True)
class Lookup:
    """The item found for a mineral, if one was, and each item Wikidata's search returned, with why it was or wasn't
    taken."""

    item: WikidataItem | None
    seen: tuple[str, ...]


@dataclass
class Found:
    """What the library found for one mineral, and what it looked at, for the audit log."""

    passages: list[Passage]
    sources_read: int
    sources_with_passages: int

    def detail(self) -> str:
        origins = sorted({p.source.origin for p in self.passages})
        return (f"{len(self.passages)} passages from {self.sources_with_passages} sources ({self.sources_read} read)"
                + (f" ({', '.join(origins)})" if origins else ""))


@dataclass
class Library:
    """The sources a run reads, each page downloaded once. Also stands in for `Web` in the mechanical checks, so a page
    the proposal cites is the page the passages came from, not a second download."""

    web: Web
    known: list[Source]
    pages: dict[str, Page] = field(default_factory=dict)
    items: dict[str, WikidataItem | None] = field(default_factory=dict)
    openalex_searches: int = 0
    openalex_failures: list[str] = field(default_factory=list)  # each search that failed, and why

    def page(self, url: str) -> Page:
        if url not in self.pages:
            self.pages[url] = self.web.page(url)
        return self.pages[url]

    def wikidata_item(self, item: str) -> WikidataItem | None:
        if item not in self.items:
            self.items[item] = self.web.wikidata_item(item)
        return self.items[item]

    def item_for(self, name: str) -> Lookup:
        """The mineral's Wikidata item, and every item the search returned with why it was or wasn't taken, so a skip
        explains itself. The item is called exactly `name` (label or alias) and is a mineral: a mineral species, or a
        subclass of a class of minerals (limonite is filed under "oxide class of minerals"). A native metal's name finds
        the element, which isn't a mineral, so a one-word name is tried again as "native <name>" (native silver).
        Raises a network error when Wikidata can't be reached, which is not the same as there being no item."""
        names = [name] + ([f"native {name.lower()}"] if len(name.split()) == 1 else [])
        seen = []
        for wanted in names:
            for found in self.web.wikidata_search(wanted):
                item = self.wikidata_item(found)
                why_not = self._why_not(item, found, wanted)
                seen.append(self._described(found, item, wanted) + (f": {why_not}" if why_not else ": taken"))
                if not why_not:
                    return Lookup(item, tuple(seen))
        return Lookup(None, tuple(seen))

    def _why_not(self, item: WikidataItem | None, found: str, name: str) -> str | None:
        if item is None:
            return "no such item"
        if item.id != found:
            return f"merged into {item.id}"
        if not item.is_called(name):
            return f"not called {name!r}"
        if not (item.is_a_mineral or self._in_a_class_of_minerals(item)):
            return "neither a mineral species nor a subclass of a class of minerals"
        return None

    def _in_a_class_of_minerals(self, item: WikidataItem) -> bool:
        # A heuristic on English labels: a subclass of anything whose label says "mineral" ("oxide class of minerals",
        # a mineral group). It could also match, say, "mineral resource"; the item must still be called exactly the
        # MRDS name, and every item taken is recorded, so a wrong one shows in the audit log and the pull request.
        return any("mineral" in (self._label(parent) or "").lower() for parent in item.subclass_of)

    def _described(self, found: str, item: WikidataItem | None, wanted: str) -> str:
        """An item the search returned, for the audit log. Only what the decision already read is named: the parents
        of an item called the name searched for (read to tell a class of minerals), and the few classes in
        CLASS_NAMES. Naming every hit's classes (albums, bands, colours) would cost a request each."""
        if item is None:
            return found
        called = item.is_called(wanted)

        def name(c: str, read: bool) -> str:
            label = CLASS_NAMES.get(c) or (self._label(c) if read else None)
            return f"{c} {label!r}" if label else c

        kinds = ", ".join(name(c, False) for c in item.instance_of) or "nothing"
        parents = ", ".join(name(c, called and not item.is_a_mineral) for c in item.subclass_of) or "nothing"
        return f"{found} {item.label!r} ({item.description or 'no description'}; instance of {kinds}; subclass of {parents})"

    def _label(self, item_id: str) -> str | None:
        if item_id in CLASS_NAMES:
            return CLASS_NAMES[item_id]
        try:
            item = self.wikidata_item(item_id)
        except NETWORK_ERRORS:
            return None
        return item.label if item else None

    def passages(self, item: WikidataItem, name: str) -> Found:
        names = {name, *((item.label,) if item.label else ())}
        sources = self.known + self._openalex_sources(name)
        # Ranked across every source, not source by source: otherwise the first sources' weaker sentences fill the places
        # before a better one is read (Magnetite, 2026-11-25). Ties keep the sources' order, the repository's first.
        candidates: list[tuple[int, int, Source, tuple[str, str, str]]] = []
        read = with_passages = 0
        for order, source in enumerate(sources):
            page = self.page(source.url)
            if not page.loaded:
                continue
            read += 1
            found = _passages_in(page.text, names, lines_are_blocks=page.kind != "pdf")[:PASSAGES_PER_SOURCE]
            with_passages += bool(found)
            candidates += [(rank, order, source, sentence) for rank, *sentence in found]
        candidates.sort(key=lambda candidate: (-candidate[0], candidate[1]))
        passages = [Passage(number, source, *sentence)
                    for number, (_, _, source, sentence) in enumerate(candidates[:PASSAGES], start=1)]
        return Found(passages, read, with_passages)

    def _openalex_sources(self, name: str) -> list[Source]:
        sources: dict[str, Source] = {}
        for search in OPENALEX_SEARCHES:
            self.openalex_searches += 1
            try:
                works = self.web.openalex_works(search.format(name=name), OPENALEX_WORKS)
            except urllib.error.HTTPError as error:
                if error.code == 429:
                    raise SourcesUnavailable(f"OpenAlex refused a search ({error}); its daily allowance is likely spent. "
                                             "Run again tomorrow, or set OPENALEX_API_KEY (ADR 0047).") from error
                self.openalex_failures.append(f"{search.format(name=name)}: {error}")
                continue
            except NETWORK_ERRORS as error:
                # OpenAlex being down, or its daily allowance spent, costs this item its OpenAlex sources, not the run;
                # it is recorded, so "no passages" can be told apart from "no answer".
                self.openalex_failures.append(f"{search.format(name=name)}: {getattr(error, 'code', '')} {error}".strip())
                continue
            for work in works:
                if work.get("type") in NOT_SOURCES or (work.get("display_name") or "").lower().startswith("correction"):
                    continue
                url = _readable_copy(work)
                if url and url not in sources and not any(s.url == url for s in self.known):
                    sources[url] = Source(openalex_citation(work), url, "OpenAlex")
        return list(sources.values())


def known_sources(root: Path, leaving_out: frozenset[str] = frozenset()) -> list[Source]:
    """The pages the repository already cites, with their citations: the ore crosswalk's (except rows left out, as an
    evaluation leaves out the rows it asks about again) and the curated layer's. A page cited only by a left-out row
    isn't offered: it would hand the agents the person's answer."""
    left_out = {name.casefold() for name in leaving_out}
    references = [row for row in ore_crosswalk_rows(root) if row["mrds_ore"].casefold() not in left_out]
    documents, _ = load_documents(root)
    for document in documents:
        references += _references_in(document.data)
    sources: dict[str, Source] = {}
    for reference in references:
        url = (reference.get("url") or "").strip()
        if url.startswith(("http://", "https://")) and url not in sources:
            sources[url] = Source(" ".join(reference["citation"].split()), url, "cited in the repository")
    return list(sources.values())


def _readable_copy(work: dict) -> str | None:
    """Where a free copy of the work can be downloaded: its PDF if OpenAlex knows one, else the page it lists."""
    best = work.get("best_oa_location") or {}
    return best.get("pdf_url") or best.get("landing_page_url") or (work.get("open_access") or {}).get("oa_url")


def openalex_citation(work: dict) -> str:
    """A reference-list citation from OpenAlex's record: authors, (year), title, and where it was published. Authors are
    named as OpenAlex names them: turning a name into "Surname, I." means guessing which part is the surname, and a
    wrong guess is an error the proposer can't fix (Cuprite, 2026-11-25)."""
    authors = [" ".join(((a.get("author") or {}).get("display_name") or "").split()) for a in work.get("authorships") or []]
    authors = [a for a in authors if a]
    names = (authors[0] + " et al." if len(authors) > 3 else
             " & ".join([", ".join(authors[:-1]), authors[-1]]) if len(authors) > 1 else "".join(authors))
    year = f" ({work['publication_year']})" if work.get("publication_year") else ""
    title = " ".join((work.get("display_name") or "").split()).rstrip(".")
    venue = (((work.get("primary_location") or {}).get("source") or {}).get("display_name") or "").strip()
    return " ".join(part for part in (f"{names}{year}." if names else f"{year.strip()}.".lstrip("."),
                                      f"{title}.", f"{venue}." if venue else "") if part).strip()


def _sentences(block: str) -> list[str]:
    """A block's sentences: split where a sentence ends, then mended where the split came after an abbreviation or an
    initial instead."""
    sentences: list[str] = []
    for piece in (p for p in SENTENCE_END.split(block) if p):
        if sentences and (ABBREVIATION.search(sentences[-1]) or INITIAL.search(sentences[-1])):
            sentences[-1] += " " + piece
        else:
            sentences.append(piece)
    return sentences


def _is_prose(sentence: str) -> bool:
    """A sentence someone wrote, not a header, footer, reference or keyword list a PDF's text runs together: eight words
    or more, mostly letters, ending as a sentence ends, and none of the marks of a reference or a page header."""
    letters = sum(c.isalpha() for c in sentence)
    return (len(sentence.split()) >= 8 and sentence.rstrip("\"”’)")[-1:] in ".!?" and letters / len(sentence) > 0.7
            and sum(c.isdigit() for c in sentence) / len(sentence) < 0.1 and not NOT_PROSE.search(sentence)
            and not CAPTION.search(sentence) and not REFERENCE_ENTRY.search(sentence))


def _passages_in(text: str, names: set[str], lines_are_blocks: bool) -> list[tuple[int, str, str, str]]:
    """The sentences that name the mineral and speak of ore or smelting, most to the point first, each with its rank and
    the sentences either side. A web page's lines are its blocks (a heading ends without a full stop); a PDF's lines are
    where the text wrapped, so they are joined, and a word it broke across two lines is mended, as the quote check
    allows."""
    if not lines_are_blocks:
        text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text).replace("\n", " ")
    sentences = [s for block in text.split("\n") for s in _sentences(" ".join(block.split()))]
    named = re.compile("|".join(rf"\b{re.escape(n)}" for n in names), re.IGNORECASE)
    shortest, longest = SENTENCE_LENGTH
    found = []
    for i, sentence in enumerate(sentences):
        after_a_label = i > 0 and CAPTION_LABEL.match(sentences[i - 1])
        if shortest <= len(sentence) <= longest and named.search(sentence) and SUBJECT.search(sentence) \
                and _is_prose(sentence) and not after_a_label:
            rank = 3 * len(SMELTING.findall(sentence)) + 2 * len(PAST.findall(sentence)) + len(SUBJECT.findall(sentence))
            found.append((rank, i, sentence))
    found.sort(key=lambda hit: (-hit[0], hit[1]))
    return [(rank, sentence, sentences[i - 1] if i else "", sentences[i + 1] if i + 1 < len(sentences) else "")
            for rank, i, sentence in found]
