"""Reading the web for the agents, in code (ADR 0048): Wikidata's items, OpenAlex's open-access works, and the pages
they lead to, as text (HTML, PDF or plain text). Code finds and reads every source; a model only judges what code
found, so nothing a model says a page says is taken on trust.
"""

from __future__ import annotations

import http.client
import io
import ipaddress
import json
import os
import re
import socket
import ssl
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser

from ..upstream import REFERENCES, USER_AGENT

TIMEOUT_S = 60
MAX_BYTES = 30 * 1024 * 1024  # a long PDF; anything bigger isn't a page someone would cite for one sentence
# Typographic variants that a quote copied by a model and the page itself may spell differently.
SAME_CHARACTER = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "“": '"', "”": '"', "„": '"', "‟": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-",
})
# Wikidata's "instance of", and the class every mineral species is an instance of.
INSTANCE_OF, SUBCLASS_OF, MINERAL_SPECIES = "P31", "P279", "Q12089225"
OPENALEX_FIELDS = "id,doi,type,display_name,publication_year,authorships,primary_location,best_oa_location,open_access"
# Where a quote leaves words out: "…", "...", "[...]" or "[…]".
ELISION = re.compile(r"\[?(?:\.\s?\.\s?\.|…)\]?")


@dataclass(frozen=True)
class Page:
    url: str
    status: str  # the HTTP status, or why it couldn't be read
    text: str = ""
    title: str | None = None
    kind: str | None = None  # html, pdf or text

    @property
    def loaded(self) -> bool:
        return self.status == "200" and bool(self.text.strip())

    @property
    def unreachable(self) -> bool:
        """The site didn't answer, or said it can't for now (too many requests, a server error): the page may still be
        there."""
        return self.status.startswith("unreachable") or self.status == "429" or self.status.startswith("5")


@dataclass(frozen=True)
class WikidataItem:
    id: str  # the item's id now: an item merged into another redirects to it
    label: str | None
    description: str | None
    aliases: tuple[str, ...] = ()
    instance_of: tuple[str, ...] = ()  # the classes it is an instance of (P31)
    subclass_of: tuple[str, ...] = ()  # the classes it is a subclass of (P279): how a kind of mineral, like limonite, is described

    def is_called(self, name: str) -> bool:
        return name.casefold() in {n.casefold() for n in (self.label, *self.aliases) if n}

    @property
    def is_a_mineral(self) -> bool:
        return MINERAL_SPECIES in self.instance_of


@dataclass(frozen=True)
class Web:
    user_agent: str = USER_AGENT
    wikidata_url: str = "https://www.wikidata.org"
    openalex_url: str = REFERENCES.url

    def wikidata_search(self, name: str) -> list[str]:
        """The ids of the items whose English label or alias matches `name`, as Wikidata's own search ranks them."""
        query = urllib.parse.urlencode({"action": "wbsearchentities", "search": name, "language": "en", "type": "item",
                                        "limit": 10, "format": "json"})
        return [hit["id"] for hit in self._json(f"{self.wikidata_url}/w/api.php?{query}").get("search") or []]

    def openalex_works(self, search: str, count: int) -> list[dict]:
        """Open-access works OpenAlex finds for `search` (in titles, abstracts and full texts), best first."""
        params = {"search": search, "filter": "is_oa:true", "per_page": count, "select": OPENALEX_FIELDS}
        if key := os.environ.get("OPENALEX_API_KEY"):  # optional: a free key raises the daily allowance (ADR 0047)
            params["api_key"] = key
        return self._json(f"{self.openalex_url}/works?{urllib.parse.urlencode(params)}").get("results") or []

    def _json(self, url: str) -> dict:
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept": "application/json"})
        with _PUBLIC_ONLY.open(request, timeout=TIMEOUT_S) as response:
            return json.loads(response.read())

    def page(self, url: str) -> Page:
        """The page at `url` as text. Only web addresses: a citation has no business pointing at a file or FTP server."""
        try:
            if urllib.parse.urlsplit(url).scheme.lower() not in ("http", "https"):
                return Page(url, "not a web address")
            if why := not_public(url):
                return Page(url, f"not a public web address: {why}")
            request = urllib.request.Request(url, headers={
                "User-Agent": self.user_agent, "Accept": "text/html,application/pdf,text/plain;q=0.9,*/*;q=0.5"})
            with _PUBLIC_ONLY.open(request, timeout=TIMEOUT_S) as response:
                body = response.read(MAX_BYTES + 1)
                content_type = response.headers.get_content_type()
                charset = response.headers.get_content_charset() or "utf-8"
                status = str(response.status)
        except urllib.error.HTTPError as error:
            return Page(url, str(error.code))
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException, ValueError) as error:
            return Page(url, f"unreachable: {getattr(error, 'reason', error)}")
        if len(body) > MAX_BYTES:
            return Page(url, f"larger than {MAX_BYTES // (1024 * 1024)} MB")
        return read(url, status, body, content_type, charset)

    def wikidata_item(self, item: str) -> WikidataItem | None:
        """The item's English label, description and aliases, or None when there is no such item."""
        if not re.fullmatch(r"Q\d+", item):
            return None
        url = f"{self.wikidata_url}/wiki/Special:EntityData/{item}.json"
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept": "application/json"})
        try:
            with _PUBLIC_ONLY.open(request, timeout=TIMEOUT_S) as response:
                entities = json.loads(response.read()).get("entities") or {}
        except urllib.error.HTTPError as error:
            if error.code in (400, 404):
                return None
            raise
        if not entities:
            return None
        # A merged item redirects: the answer is keyed by the item it was merged into.
        current, entity = next(iter(entities.items()))
        english = lambda field: ((entity.get(field) or {}).get("en") or {})  # noqa: E731
        return WikidataItem(
            id=current,
            label=english("labels").get("value"),
            description=english("descriptions").get("value"),
            aliases=tuple(alias["value"] for alias in (entity.get("aliases") or {}).get("en") or []),
            instance_of=_claimed(entity, INSTANCE_OF),
            subclass_of=_claimed(entity, SUBCLASS_OF),
        )


def not_public(url: str) -> str | None:
    """Why a URL isn't on the public web, or None if it is. The agent chooses what the pipeline downloads, after reading
    pages that may tell it what to cite, so a citation must never lead the pipeline to this machine or its network (the
    Dagster UI, the app's server, a router)."""
    host = urllib.parse.urlsplit(url).hostname
    if not host:
        return "no host"
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except (socket.gaierror, UnicodeError):
        return None  # nothing to connect to: the download fails as unreachable, which says it better
    for address in addresses:
        if not ipaddress.ip_address(address.split("%")[0]).is_global:
            return f"{host} is {address}, a private, loopback or reserved address"
    return None


class _PublicRedirects(urllib.request.HTTPRedirectHandler):
    """Follows a redirect only to the public web: a public page mustn't be able to send the download somewhere private."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if why := not_public(newurl):
            raise urllib.error.URLError(f"redirected to {newurl}, not a public web address: {why}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _system_trust() -> ssl.SSLContext:
    """Certificates checked against the operating system's trusted roots, as a browser or curl checks them. Python's
    own bundle can lack a root the system trusts, and fail a site every browser opens (Azurite's source, 2026-11-25)."""
    import truststore

    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


_PUBLIC_ONLY = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_system_trust()), _PublicRedirects)


def _claimed(entity: dict, prop: str) -> tuple[str, ...]:
    """The items a property's statements point to (an item's classes, for P31 and P279)."""
    return tuple(claim["mainsnak"]["datavalue"]["value"]["id"] for claim in (entity.get("claims") or {}).get(prop) or []
                 if (claim.get("mainsnak") or {}).get("datavalue"))


def read(url: str, status: str, body: bytes, content_type: str, charset: str) -> Page:
    if content_type == "application/pdf" or body.startswith(b"%PDF"):
        return Page(url, status, pdf_text(body), kind="pdf")
    try:
        text = body.decode(charset, errors="replace")
    except LookupError:  # a charset Python doesn't know: most pages that name one are UTF-8 anyway
        text = body.decode("utf-8", errors="replace")
    if "html" in content_type or text.lstrip().startswith("<"):
        title, text = html_text(text)
        return Page(url, status, text, title, kind="html")
    if content_type.startswith("text/"):
        return Page(url, status, text, kind="text")
    return Page(url, f"not a page we can read ({content_type})")


class _Text(HTMLParser):
    """A page's readable text: no scripts or styles, and a line break wherever a block of text ends."""

    SKIPPED = {"script", "style", "noscript", "template", "svg", "head"}
    BLOCKS = {"p", "div", "br", "li", "ul", "ol", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6", "section",
              "article", "blockquote", "figcaption", "dd", "dt", "header", "footer", "main", "aside", "table", "hr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title: list[str] = []
        self.skipping = 0
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True
        elif tag in self.SKIPPED:
            self.skipping += 1
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif tag in self.SKIPPED:
            self.skipping = max(0, self.skipping - 1)
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
        elif not self.skipping:
            self.parts.append(data)


def html_text(html: str) -> tuple[str | None, str]:
    parser = _Text()
    parser.feed(html)
    parser.close()
    title = " ".join("".join(parser.title).split()) or None
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    return title, "\n".join(line for line in lines if line)


def pdf_text(body: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(body)).pages)
    except (PdfReadError, ValueError, KeyError, TypeError):
        return ""


def readable(text: str) -> str:
    """Text with its typography made plain (curly quotes, dashes, ligatures, soft hyphens) and its spacing collapsed,
    so a quote and the page can be compared word for word."""
    text = unicodedata.normalize("NFKC", text).replace("­", "").translate(SAME_CHARACTER)
    return re.sub(r"\s+", " ", text).strip()


def locate(quote: str, text: str) -> tuple[str, int] | None:
    """Where the quote is in the text, ignoring case and typography: the readable text and the position, or None.
    Words a quote leaves out ("…") may be anything, but what it keeps must appear in order. A word a PDF broke across
    two lines ("oxi-\\ndised") may be quoted whole."""
    fragments = [readable(part).lower() for part in ELISION.split(quote)]
    fragments = [fragment.strip(" .,;:") for fragment in fragments if fragment.strip(" .,;:")]
    if not fragments:
        return None
    for haystack in (readable(text), readable(re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text))):
        lowered, start, position = haystack.lower(), None, 0
        for fragment in fragments:
            found = lowered.find(fragment, position)
            if found < 0:
                break
            start = found if start is None else start
            position = found + len(fragment)
        else:
            return haystack, start
    return None


def excerpt(text: str, position: int, around: int = 2500) -> str:
    """The text around a position: what a reviewer reads to judge a quote in its context."""
    start, end = max(0, position - around), min(len(text), position + around)
    return ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")
