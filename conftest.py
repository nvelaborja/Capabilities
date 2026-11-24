import csv
import gzip
import io
import json
import shutil
import threading
import zipfile
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from capabilities.graph import Graph

REPO_ROOT = Path(__file__).resolve().parent


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def graph(built_dir) -> Graph:
    """The graph the app reads: the curated layer built with the upstream datasets' cold backups (ADR 0044)."""
    from capabilities.built import load_built

    return load_built(REPO_ROOT, built_dir)


@pytest.fixture(scope="session")
def curated_graph() -> Graph:
    """The curated YAML alone, as people wrote it."""
    return Graph.from_curated(REPO_ROOT)


@pytest.fixture(scope="session")
def built_dir(tmp_path_factory) -> Path:
    """The repository's graph, built once per test run into a temporary directory (never the repo's build/). Nothing is
    downloaded, so it uses the cold backups in snapshots/, as CI and a fresh clone do."""
    from capabilities.built import run_build

    build_dir = tmp_path_factory.mktemp("build")
    run_build(REPO_ROOT, build_dir)
    return build_dir


# Fourteen real MRDS records (US public domain), picked to cover every rule in data/crosswalks/mrds_sources.csv.
SAMPLE = REPO_ROOT / "pipeline" / "tests" / "fixtures" / "mrds-sample.csv"


def _mrds_zip(directory: Path, rows: list[dict] | None = None, columns: list[str] | None = None) -> str:
    """A zip shaped like USGS's mrds-csv.zip, holding the sample or the given rows, as a file:// URL."""
    with SAMPLE.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        rows = rows if rows is not None else list(reader)
        columns = columns or reader.fieldnames
    directory.mkdir(parents=True, exist_ok=True)
    data = directory / "mrds.csv"
    with data.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    archive = directory / "mrds-csv.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.write(data, "mrds.csv")
    return archive.as_uri()


def _sample_rows() -> list[dict]:
    with SAMPLE.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


@pytest.fixture(scope="session")
def mrds_zip():
    """Makes a zip shaped like USGS's mrds-csv.zip from the sample (or given rows), and returns it as a file:// URL."""
    return _mrds_zip


# Thirteen real Pleiades places (CC BY 3.0), picked to cover each case of ADR 0046: a copper mine by tag (Agrokipia), by
# its description only (Chale Ghar 1), and one dated "to the Iron Age" that is no iron mine (Almyras); limestone and
# granite quarries; a mine of four metals (Dognecea); a gold mine no rule matches (Dolaucothi); an untitled quarry with a
# rough location; a tin mine named in its description; Grimes Graves (flint); a settlement (Athens); an unlocated mine;
# and a copper mine with a rough location (Temesa).
PLEIADES_SAMPLE = REPO_ROOT / "pipeline" / "tests" / "fixtures" / "pleiades-sample.csv"


@pytest.fixture(scope="session")
def pleiades_gz(tmp_path_factory) -> str:
    """The Pleiades sample, gzipped like the daily dump, as a file:// URL."""
    archive = tmp_path_factory.mktemp("pleiades-download") / "pleiades-places-latest.csv.gz"
    archive.write_bytes(gzip.compress(PLEIADES_SAMPLE.read_bytes()))
    return archive.as_uri()


@pytest.fixture(scope="session")
def sample_rows():
    """Returns the sample's rows, as dictionaries, to change before zipping."""
    return _sample_rows


# Four real Wikidata hardness statements (CC0), retrieved 2026-11-24, for hematite, limonite, granite and copper. Our
# curated values match them since ADR 0043 was accepted; tests that need a disagreement change a curated value.
WIKIDATA_SAMPLE = REPO_ROOT / "pipeline" / "tests" / "fixtures" / "wikidata-sample.csv"
# The labels, descriptions and formulas of every crosswalked item: the committed backup (CC0), answered as CSV. Every
# crosswalked item must be in it (ADR 0044), so a sample would have to list them all anyway.
WIKIDATA_ITEMS_BACKUP = REPO_ROOT / "snapshots" / "wikidata_items" / "wikidata_items.parquet"


def _items_csv() -> bytes:
    import duckdb

    rows = duckdb.sql("select item, label, description, formula from read_parquet(?) order by all",
                      params=[str(WIKIDATA_ITEMS_BACKUP)]).fetchall()
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["item", "label", "description", "formula"])
    writer.writerows(rows)
    return out.getvalue().encode()


class _SparqlEndpoint(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"])).decode()
        query = parse_qs(body)["query"][0]
        self.server.queries.append(query)
        # Each of our two queries gets its own answer: the labels query asks for rdfs:label.
        result = _items_csv() if "rdfs:label" in query else WIKIDATA_SAMPLE.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/csv")
        self.send_header("Content-Length", str(len(result)))
        self.end_headers()
        self.wfile.write(result)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="session")
def wikidata_endpoint():
    """A local stand-in for Wikidata's SPARQL endpoint, so tests never use the network: it answers each query with the
    matching sample and keeps the queries it was sent."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SparqlEndpoint)
    server.queries = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield SimpleNamespace(url=f"http://127.0.0.1:{server.server_port}/sparql", queries=server.queries)
    server.shutdown()


# What OpenAlex and Crossref answered for every cited work, and how every cited link answered: the committed backup
# (OpenAlex CC0; Crossref's bibliographic metadata, no abstracts). The stand-in rebuilds each response from it, so a
# download through the stand-in gives back the backup, and nothing in the tests asks the real services (ADR 0047).
REFERENCES_BACKUP = REPO_ROOT / "snapshots" / "reference_candidates" / "reference_candidates.parquet"


def _reference_rows() -> list[dict]:
    import duckdb

    relation = duckdb.sql("select * from read_parquet(?)", params=[str(REFERENCES_BACKUP)])
    return [dict(zip(relation.columns, row)) for row in relation.fetchall()]


def _openalex_work(row: dict) -> dict:
    return {
        "id": row["record_id"],
        "doi": f"https://doi.org/{row['doi']}" if row["doi"] else None,
        "display_name": row["title"],
        "publication_year": int(row["year"]) if row["year"] else None,
        "authorships": [{"author": {"display_name": name}} for name in row["authors"].split("; ")] if row["authors"] else [],
        "type": row["type"],
        "open_access": {"oa_url": row["oa_url"]},
        "best_oa_location": {"pdf_url": row["pdf_url"]} if row["pdf_url"] else None,
    }


def _crossref_work(row: dict) -> dict:
    work = {
        "DOI": row["doi"],
        "title": [row["title"]] if row["title"] else [],
        "issued": {"date-parts": [[int(row["year"]) if row["year"] else None]]},
        "type": row["type"],
        "score": json.loads(row["score"]) if row["score"] else None,
    }
    if row["authors"]:
        work["author"] = [{"name": name} for name in row["authors"].split("; ")]
    return work


class _ScholarlyEndpoint(BaseHTTPRequestHandler):
    """OpenAlex under /openalex and Crossref under /crossref: /works?search= (or ?query.bibliographic=) and /works/<doi>."""

    def do_GET(self):
        url = urlparse(self.path)
        service, _, path = url.path.lstrip("/").partition("/")
        self.server.requests.append(self.path)
        if path == "works":
            params = parse_qs(url.query)
            lookup, query = "search", params["search" if service == "openalex" else "query.bibliographic"][0]
        else:
            lookup, query = "doi", unquote(path.removeprefix("works/")).removeprefix("doi:")
        answered = [row for row in self.server.rows
                    if (row["service"], row["lookup"], row["query"]) == (service, lookup, query) and row["rank"]]
        # Two citations can send the same search (the same paper, cited directly and as summarized); the service gave
        # both the same answer, so one of them is the answer.
        first = min((row["citation"] for row in answered), default=None)
        candidates = sorted((row for row in answered if row["citation"] == first), key=lambda row: int(row["rank"]))
        work = _openalex_work if service == "openalex" else _crossref_work
        if lookup == "doi" and not candidates:
            return self._send(404, {})
        if lookup == "doi":
            body = work(candidates[0]) if service == "openalex" else {"message": work(candidates[0])}
        else:
            works = [work(row) for row in candidates]
            body = {"results": works} if service == "openalex" else {"message": {"items": works}}
        self._send(200, body)

    def _send(self, status: int, body: dict):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="session")
def scholarly_endpoint():
    """A local stand-in for the OpenAlex and Crossref APIs, answering from the committed backup, and keeping the requests
    it was sent. `links` is how each cited link answered when the backup was made."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ScholarlyEndpoint)
    server.rows, server.requests = _reference_rows(), []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    links = {row["query"]: row["status"] for row in server.rows if row["service"] == "link"}
    yield SimpleNamespace(openalex_url=f"{base}/openalex", crossref_url=f"{base}/crossref", requests=server.requests,
                          links=links)
    server.shutdown()


@contextmanager
def offline_lookups(links: dict[str, str]):
    """Reference lookups with no waiting between requests, and every cited link answered from `links` (200 when it isn't
    listed) instead of the web."""
    from capabilities_pipeline import citations

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(citations, "pause", lambda seconds: None)
        patch.setattr(citations.Lookups, "open_link", lambda self, url: links.get(url, "200"))
        yield


@pytest.fixture(scope="session")
def lookups_offline(scholarly_endpoint):
    """Returns a context in which reference lookups never wait and never touch the web (see offline_lookups)."""
    return lambda: offline_lookups(scholarly_endpoint.links)


@pytest.fixture(scope="session")
def fetch_references(scholarly_endpoint):
    """Downloads the reference candidates through the stand-in into a build directory, for the given data root."""
    from dataclasses import replace

    from capabilities_pipeline.upstream import REFERENCES, fetch

    def download(build_dir: Path, root: Path = REPO_ROOT, links: dict[str, str] | None = None) -> dict:
        dataset = replace(REFERENCES, crossref_url=scholarly_endpoint.crossref_url)
        with offline_lookups(scholarly_endpoint.links | (links or {})):
            return fetch(dataset, build_dir, scholarly_endpoint.openalex_url, root=root)

    return download


@pytest.fixture(scope="session")
def upstream_built_dir(tmp_path_factory, mrds_zip, wikidata_endpoint, pleiades_gz, fetch_references) -> Path:
    """The repository's graph built once with snapshots of the MRDS and Wikidata samples, so it has source occurrences
    and upstream quantity values."""
    from capabilities.built import run_build
    from capabilities_pipeline.upstream import MRDS, PLEIADES, WIKIDATA, WIKIDATA_ITEMS, fetch

    build_dir = tmp_path_factory.mktemp("upstream-build")
    fetch(MRDS, build_dir, mrds_zip(tmp_path_factory.mktemp("mrds-download")))
    fetch(WIKIDATA, build_dir, wikidata_endpoint.url, root=REPO_ROOT)
    fetch(WIKIDATA_ITEMS, build_dir, wikidata_endpoint.url, root=REPO_ROOT)
    fetch(PLEIADES, build_dir, pleiades_gz)
    fetch_references(build_dir)
    run_build(REPO_ROOT, build_dir)
    return build_dir


@pytest.fixture
def data_copy(tmp_path: Path) -> Path:
    """A throwaway copy of the schemas and data, for tests that break files on purpose."""
    for directory in ("schema", "data", "examples"):
        shutil.copytree(REPO_ROOT / directory, tmp_path / directory)
    # The cold backups of the upstream datasets, which every build needs (ADR 0044). Linked, not copied: no test changes
    # them, and MRDS's is 15 MB.
    (tmp_path / "snapshots").symlink_to(REPO_ROOT / "snapshots", target_is_directory=True)
    return tmp_path


GRANITE_OVERRIDE = """id: {id}
kind: override
thing: {thing}
quantity: hardness_mohs
value: [6, 7]
replaces: {{ dataset: wikidata, value: {replaces} }}
reason: Granite's common minerals, quartz and feldspar, are 6 to 7; 5 is softer than either.
references:
  - citation: "Klein, C. & Dutrow, B. (2007). Manual of Mineral Science, 23rd ed. Wiley."
    supports: Mohs hardness of quartz and feldspar.
    status: unverified
"""


@pytest.fixture
def write_override():
    """Writes an override of a thing's hardness into a copy of the data: by default granite's, replacing Wikidata's 5–7
    with 6–7."""
    def write(root: Path, id: str = "granite-hardness", thing: str = "granite", replaces: str = "[5, 7]") -> Path:
        path = root / "data" / "overrides" / f"{id}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(GRANITE_OVERRIDE.format(id=id, thing=thing, replaces=replaces), encoding="utf-8")
        return path

    return write


def _route(route_id: str, achieves: dict, requires: list[dict], **extra) -> dict:
    route = {"id": route_id, "kind": "route", "label": route_id.replace("-", " ").capitalize(), "achieves": achieves,
             "requires": requires, "references": []}
    if "thing" in achieves:
        route["outputs"] = [{"thing": achieves["thing"]}]
    return {**route, **extra}


@pytest.fixture
def workshop(tmp_path: Path) -> Graph:
    """A small synthetic graph with a cycle, a heat threshold, a category, and a target-relative condition.

    Levels by construction: wood, flint, granite 0; knife 1; ember 2 (via wood + knife, not via charcoal);
    charcoal 3; pot 2 (the open fire is hot enough); metal 5 (only the furnace is); relic has no route.
    Flint is regional, so with nothing selected only the open fire is reachable.
    """
    def material(thing_id, natural=True, **extra):
        thing = {"id": thing_id, "kind": "material", "label": thing_id.capitalize(), "origin": "natural" if natural else "produced"}
        if natural:
            thing["availability"] = "ubiquitous"
        return {**thing, **extra}

    heat_at_least = lambda temperature: {"role": "effect", "effect": "heat",  # noqa: E731
                                         "where": [{"quantity": "temperature_c", "op": ">=", "value": temperature}]}
    things = {
        "wood": material("wood", quantities={"hardness_mohs": 2}),
        "flint": material("flint", availability="regional"),
        "granite": material("granite", availability="regional", quantities={"hardness_mohs": [6, 7]}),
        "knife": {"id": "knife", "kind": "artifact", "label": "Knife", "is_a": ["blade"], "quantities": {"hardness_mohs": 5}},
        "ember": material("ember", natural=False),
        "charcoal": material("charcoal", natural=False),
        "pot": {"id": "pot", "kind": "artifact", "label": "Pot"},
        "metal": material("metal", natural=False),
        "relic": {"id": "relic", "kind": "artifact", "label": "Relic"},
        "blade": {"id": "blade", "kind": "category", "label": "Blade"},
        "heat": {"id": "heat", "kind": "effect", "label": "Heat", "dimensions": ["temperature_c"]},
        "knapping": {"id": "knapping", "kind": "technique", "label": "Knapping"},
    }
    routes = [
        _route("knap-knife", {"thing": "knife"}, [{"role": "consumed", "thing": "flint"}], techniques=["knapping"]),
        _route("ember-from-charcoal", {"thing": "ember"}, [{"role": "consumed", "thing": "charcoal"}]),
        _route("ember-by-friction", {"thing": "ember"}, [{"role": "consumed", "thing": "wood"}, {"role": "tool", "category": "blade"}]),
        _route("char-wood", {"thing": "charcoal"}, [{"role": "consumed", "thing": "wood"}, {"role": "consumed", "thing": "ember"}]),
        _route("open-fire", {"effect": "heat"}, [{"role": "consumed", "thing": "wood"}], provides={"temperature_c": [600, 800]}),
        _route("furnace", {"effect": "heat"}, [{"role": "consumed", "thing": "charcoal"}], provides={"temperature_c": 1200}),
        _route("fire-pot", {"thing": "pot"}, [heat_at_least(500)]),
        _route("smelt-metal", {"thing": "metal"}, [heat_at_least(1000), {"role": "consumed", "thing": "ember"}]),
        _route("cut-with-blade", {"verb": "cut"}, [{"role": "tool", "category": "blade",
                                                   "where": [{"quantity": "hardness_mohs", "op": ">=", "value": "target.hardness_mohs"}]}]),
    ]
    return Graph(
        tmp_path,
        quantities={
            "temperature_c": {"id": "temperature_c", "kind": "quantity", "label": "Temperature", "unit": "°C"},
            "hardness_mohs": {"id": "hardness_mohs", "kind": "quantity", "label": "Hardness (Mohs)", "unit": "Mohs"},
        },
        things=things,
        verbs={"cut": {"id": "cut", "kind": "verb", "label": "Cut", "params": {"target": {"kinds": ["material"]}}}},
        routes={route["id"]: route for route in routes},
    )
