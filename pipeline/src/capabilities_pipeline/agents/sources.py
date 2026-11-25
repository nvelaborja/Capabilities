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
from .web import Page, Web, WikidataItem

# Sentences worth a model's attention name the mineral and one of these.
SUBJECT = re.compile(r"\b(smelt\w*|ores?|roast\w*|furnaces?|slags?|bloom\w*|copper|iron|tin|metal\w*|min(e|ed|ing)|"
                     r"reduc\w*|sulph\w*|sulf\w*|flux\w*)\b", re.IGNORECASE)
# What ranks a sentence higher: smelting itself, and the past (the graph is about doing it by hand, ADR 0032).
SMELTING = re.compile(r"\b(smelt\w*|roast\w*|bloomer\w*|crucibles?|furnaces?)\b", re.IGNORECASE)
PAST = re.compile(r"\b(ancient|prehistor\w*|bronze age|iron age|chalcolithic|neolithic|roman|medieval|antiquity|"
                  r"archaeo\w*|early|historic\w*|BC|BCE)\b", re.IGNORECASE)
# What isn't a sentence of prose: a link, a DOI, a header or footer, a reference, a keyword list.
NOT_PROSE = re.compile(r"https?://|doi|\bvol\b|©|keywords?:|isbn|issn|et al\.,? \(?\d{4}|\d+\s*[–-]\s*\d+\s*$",
                       re.IGNORECASE)
SENTENCE_END = re.compile(r"(?<=[.!?])[\"”’)]?\s+(?=[\"“‘(]?[A-Z0-9])")
SENTENCE_LENGTH = (40, 1000)  # what a quote may be (ore_candidates.QUOTE_LENGTH)
# Archaeometallurgy first: a plain "smelting" finds mostly today's industry, and "ore" its mineral processing.
OPENALEX_SEARCHES = ("{name} archaeometallurgy", "{name} ancient smelting")
# Works that aren't a source for a claim: corrections, data deposits, front matter.
NOT_SOURCES = {"erratum", "dataset", "paratext", "editorial", "retraction", "peer-review", "letter", "other"}
OPENALEX_WORKS = 5  # per search
PASSAGES_PER_SOURCE = 3
PASSAGES = 12
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

    def item_for(self, name: str) -> WikidataItem | None:
        """The mineral's Wikidata item: called exactly `name`, and a mineral species. Raises a network error when
        Wikidata can't be reached, which is not the same as there being no item."""
        for found in self.web.wikidata_search(name):
            item = self.wikidata_item(found)
            if item and item.id == found and item.is_called(name) and item.is_a_mineral:
                return item
        return None

    def passages(self, item: WikidataItem, name: str) -> Found:
        names = {name, *((item.label,) if item.label else ())}
        sources = self.known + self._openalex_sources(name)
        passages: list[Passage] = []
        read = with_passages = 0
        for source in sources:
            page = self.page(source.url)
            if not page.loaded:
                continue
            read += 1
            found = _passages_in(page.text, names, lines_are_blocks=page.kind != "pdf")[:PASSAGES_PER_SOURCE]
            with_passages += bool(found)
            passages += [Passage(len(passages) + i + 1, source, *sentence) for i, sentence in enumerate(found)]
            if len(passages) >= PASSAGES:
                break
        return Found(passages[:PASSAGES], read, with_passages)

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
    """A reference-list citation from OpenAlex's record: authors, (year), title, and where it was published."""
    authors = [_surname_first((a.get("author") or {}).get("display_name") or "") for a in work.get("authorships") or []]
    authors = [a for a in authors if a]
    names = (authors[0] + " et al." if len(authors) > 3 else
             " & ".join([", ".join(authors[:-1]), authors[-1]]) if len(authors) > 1 else "".join(authors))
    year = f" ({work['publication_year']})" if work.get("publication_year") else ""
    title = " ".join((work.get("display_name") or "").split()).rstrip(".")
    venue = (((work.get("primary_location") or {}).get("source") or {}).get("display_name") or "").strip()
    return " ".join(part for part in (f"{names}{year}." if names else f"{year.strip()}.".lstrip("."),
                                      f"{title}.", f"{venue}." if venue else "") if part).strip()


def _is_prose(sentence: str) -> bool:
    """A sentence someone wrote, not a header, footer, reference or keyword list a PDF's text runs together: eight words
    or more, mostly letters, ending as a sentence ends, and none of the marks of a reference or a page header."""
    letters = sum(c.isalpha() for c in sentence)
    return (len(sentence.split()) >= 8 and sentence.rstrip("\"”’)")[-1:] in ".!?" and letters / len(sentence) > 0.7
            and sum(c.isdigit() for c in sentence) / len(sentence) < 0.05 and not NOT_PROSE.search(sentence))


def _surname_first(name: str) -> str:
    parts = name.split()
    if len(parts) < 2:
        return name
    initials = " ".join(f"{p[0]}." for p in parts[:-1] if p[0].isalpha())
    return f"{parts[-1]}, {initials}"


def _passages_in(text: str, names: set[str], lines_are_blocks: bool) -> list[tuple[str, str, str]]:
    """The sentences that name the mineral and speak of ore or smelting, most to the point first, each with the
    sentences either side. A web page's lines are its blocks (a heading ends without a full stop); a PDF's lines are
    where the text wrapped, so they are joined, and a word it broke across two lines is mended, as the quote check
    allows."""
    if not lines_are_blocks:
        text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text).replace("\n", " ")
    sentences = [s for block in text.split("\n") for s in SENTENCE_END.split(" ".join(block.split())) if s]
    named = re.compile("|".join(rf"\b{re.escape(n)}" for n in names), re.IGNORECASE)
    shortest, longest = SENTENCE_LENGTH
    found = []
    for i, sentence in enumerate(sentences):
        if shortest <= len(sentence) <= longest and named.search(sentence) and SUBJECT.search(sentence) \
                and _is_prose(sentence):
            rank = 3 * len(SMELTING.findall(sentence)) + 2 * len(PAST.findall(sentence)) + len(SUBJECT.findall(sentence))
            found.append((rank, i, sentence))
    found.sort(key=lambda hit: (-hit[0], hit[1]))
    return [(sentence, sentences[i - 1] if i else "", sentences[i + 1] if i + 1 < len(sentences) else "")
            for _, i, sentence in found]
