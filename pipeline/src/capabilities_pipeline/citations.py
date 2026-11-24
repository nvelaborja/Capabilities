"""Looking up the works the curated layer cites, in OpenAlex and Crossref, and checking their links (ADR 0047).

What is looked up comes from the curated layer: every distinct citation, in the YAML and in the ore crosswalk. A work is
looked up when it has a DOI, by the DOI, or a year of publication in brackets, by searching for it: OpenAlex by its title,
Crossref by the whole citation (`query.bibliographic`, made for matching citations). Anything else (a web page, a
handbook with no year) only has its link checked. Every link is checked: does it still load?

The result is kept as published, a few candidates per work, and scored by dbt. Nothing here decides whether a candidate
is the work cited, and nothing changes a reference's status: a person reads the work and changes the YAML.
"""

from __future__ import annotations

import csv
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from capabilities.graph import load_documents, ore_crosswalk_rows

# Enough to find the work when the search ranks it a little lower; Crossref's own advice is 2 to 5 rows for a query.
CANDIDATES = 5
OPENALEX_FIELDS = "id,doi,display_name,publication_year,authorships,type,open_access,best_oa_location"
# One row per candidate found, per lookup that found none, and per link checked. Every column is text.
COLUMNS = (
    "citation", "service", "lookup", "query", "status", "rank", "record_id", "doi", "title", "year", "authors", "type",
    "oa_url", "pdf_url", "score",
)
YEAR = re.compile(r"\((\d{4})\)[.:,]?\s*")
# An edition, or the summary a secondary reference was read in: not part of the title.
EDITION = re.compile(r"(,\s*\d+(st|nd|rd|th) ed\.?|,\s+as summari[sz]ed in .*)$")
TIMEOUT_S = 60


@dataclass(frozen=True)
class CitedWork:
    citation: str
    doi: str | None
    urls: tuple[str, ...]

    @property
    def searchable(self) -> bool:
        """A book or paper: it has a DOI, or a year of publication in brackets. Web pages and undated handbooks aren't
        searched; OpenAlex and Crossref list neither."""
        return bool(self.doi or YEAR.search(self.citation))


def cited_works(root: Path) -> list[CitedWork]:
    """Every distinct work the curated layer cites, by its citation, with the DOI given for it (if any use gives one)
    and every URL its uses give. The ore crosswalk's references count too, except on rows rejected (class none): they
    build nothing."""
    references: list[dict] = []
    documents, _ = load_documents(root)
    for document in documents:
        references.extend(_references_in(document.data))
    references.extend(row for row in ore_crosswalk_rows(root) if row.get("class") != "none" and row.get("citation"))
    works: dict[str, dict] = {}
    for reference in references:
        work = works.setdefault(reference["citation"].strip(), {"dois": set(), "urls": set()})
        if reference.get("doi"):
            work["dois"].add(reference["doi"].strip())
        if reference.get("url"):
            work["urls"].add(reference["url"].strip())
    # The largest DOI, when uses disagree: the same choice dbt makes (max), so both sides mean the same work.
    return [CitedWork(citation, max(work["dois"], default=None), tuple(sorted(work["urls"])))
            for citation, work in sorted(works.items())]


def _references_in(value) -> list[dict]:
    """Every reference in a document, however deeply nested (a route's, a profile item's, an override's)."""
    found = []
    if isinstance(value, dict):
        if "citation" in value and "status" in value:
            found.append(value)
        for child in value.values():
            found.extend(_references_in(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_references_in(child))
    return found


def search_text(citation: str) -> str:
    """The title to search OpenAlex for: what follows the year, up to the first full stop, without an edition. A
    citation whose year comes last (a report) is searched by what comes before it."""
    match = YEAR.search(citation)
    if not match:
        return citation
    title = re.split(r"\.\s", citation[match.end():], maxsplit=1)[0].strip(" .'\"‘’“”")
    title = EDITION.sub("", title)
    return title or citation[:match.start()].strip(" .,")


@dataclass
class Lookups:
    """Asks OpenAlex and Crossref about works, and checks links, writing what came back as rows."""

    openalex_url: str
    crossref_url: str
    user_agent: str
    # Crossref's anonymous limit for searches is one a second (ADR 0047); OpenAlex allows ten.
    pause_s: float = 1.0
    rows: list[dict] = field(default_factory=list)

    def work(self, work: CitedWork) -> None:
        if not work.searchable:
            return
        if work.doi:
            self._openalex(work, "doi", work.doi, f"/works/doi:{_quote(work.doi)}?select={OPENALEX_FIELDS}")
            self._crossref(work, "doi", work.doi, f"/works/{_quote(work.doi)}")
        else:
            title = search_text(work.citation)
            self._openalex(work, "search", title, "/works?" + urllib.parse.urlencode(
                {"search": title, "per_page": CANDIDATES, "select": OPENALEX_FIELDS}))
            self._crossref(work, "search", work.citation, "/works?" + urllib.parse.urlencode(
                {"query.bibliographic": work.citation, "rows": CANDIDATES}))

    def link(self, url: str) -> None:
        status = self.open_link(url)
        self.rows.append({"service": "link", "lookup": "link", "query": url, "status": status})

    def _openalex(self, work: CitedWork, lookup: str, query: str, path: str) -> None:
        key = os.environ.get("OPENALEX_API_KEY")  # optional: a free key raises the daily allowance (ADR 0047)
        url = self.openalex_url + path + (("&" if "?" in path else "?") + urllib.parse.urlencode({"api_key": key}) if key else "")
        status, body = self._get(url, self.pause_s / 10)
        results = (body.get("results", []) if lookup == "search" else [body]) if body else []
        self._add(work, "openalex", lookup, query, status, [_openalex_row(result) for result in results[:CANDIDATES]])

    def _crossref(self, work: CitedWork, lookup: str, query: str, path: str) -> None:
        status, body = self._get(self.crossref_url + path, self.pause_s)
        message = body.get("message", {}) if body else {}
        results = message.get("items", []) if lookup == "search" else ([message] if message else [])
        self._add(work, "crossref", lookup, query, status, [_crossref_row(result) for result in results[:CANDIDATES]])

    def _add(self, work: CitedWork, service: str, lookup: str, query: str, status: str, candidates: list[dict]) -> None:
        common = {"citation": work.citation, "service": service, "lookup": lookup, "query": query, "status": status}
        if not candidates:  # asked, and nothing came back: not the same as never asked
            self.rows.append(common)
        for rank, candidate in enumerate(candidates, start=1):
            self.rows.append({**common, "rank": str(rank), **candidate})

    def _get(self, url: str, pause_s: float) -> tuple[str, dict | None]:
        """A JSON response and its status. A work that isn't there (404) is an answer; being told to slow down, or a
        server error, is retried a few times and then raised, so the download falls back to the cold backup."""
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept": "application/json"})
        for attempt in range(4):
            pause(pause_s * (2 ** attempt if attempt else 1))
            try:
                with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                    return str(response.status), json.loads(response.read())
            except urllib.error.HTTPError as error:
                if error.code in (400, 404, 410):
                    return str(error.code), None
                if attempt == 3:
                    raise
        raise AssertionError("unreachable")

    def open_link(self, url: str) -> str:
        """Whether a link still loads: its HTTP status after redirects, or why it couldn't be reached."""
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        pause(self.pause_s / 4)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                response.read(1)
                return str(response.status)
        except urllib.error.HTTPError as error:
            return str(error.code)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            return f"unreachable: {getattr(error, 'reason', error)}"


def pause(seconds: float) -> None:
    """Wait between requests, to stay inside the services' rate limits."""
    time.sleep(seconds)


def _quote(doi: str) -> str:
    return urllib.parse.quote(doi, safe="/:")


def _openalex_row(work: dict) -> dict:
    best = work.get("best_oa_location") or {}
    return {
        "record_id": work.get("id"),
        "doi": _bare_doi(work.get("doi")),
        "title": work.get("display_name"),
        "year": _text(work.get("publication_year")),
        "authors": "; ".join((a.get("author") or {}).get("display_name") or a.get("raw_author_name") or ""
                             for a in work.get("authorships") or []),
        "type": work.get("type"),
        "oa_url": (work.get("open_access") or {}).get("oa_url"),
        "pdf_url": best.get("pdf_url"),
    }


def _crossref_row(work: dict) -> dict:
    # Abstracts can be copyrighted (ADR 0037): only these fields are kept.
    people = work.get("author") or work.get("editor") or []
    issued = (work.get("issued") or work.get("published") or {}).get("date-parts") or [[None]]
    return {
        "record_id": _bare_doi(work.get("DOI")),
        "doi": _bare_doi(work.get("DOI")),
        "title": ": ".join((work.get("title") or [""])[:1] + (work.get("subtitle") or [])[:1]),
        "year": _text(issued[0][0] if issued and issued[0] else None),
        "authors": "; ".join(" ".join(part for part in (p.get("given"), p.get("family") or p.get("name")) if part)
                             for p in people),
        "type": work.get("type"),
        "score": _text(work.get("score")),
    }


def _bare_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE).lower()


def _text(value) -> str | None:
    return None if value is None else str(value)


def write_rows(rows: list[dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
