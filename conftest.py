import csv
import shutil
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs

import pytest

from capabilities.graph import Graph

REPO_ROOT = Path(__file__).resolve().parent


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def graph() -> Graph:
    return Graph.from_curated(REPO_ROOT)


@pytest.fixture(scope="session")
def built_dir(tmp_path_factory) -> Path:
    """The repository's graph, built once per test run into a temporary directory (never the repo's build/)."""
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


@pytest.fixture(scope="session")
def sample_rows():
    """Returns the sample's rows, as dictionaries, to change before zipping."""
    return _sample_rows


# Four real Wikidata hardness statements (CC0), retrieved 2026-11-24, for hematite, limonite, granite and copper. Our
# curated values match them since ADR 0043 was accepted; tests that need a disagreement change a curated value.
WIKIDATA_SAMPLE = REPO_ROOT / "pipeline" / "tests" / "fixtures" / "wikidata-sample.csv"


class _SparqlEndpoint(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"])).decode()
        self.server.queries.append(parse_qs(body)["query"][0])
        result = WIKIDATA_SAMPLE.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/csv")
        self.send_header("Content-Length", str(len(result)))
        self.end_headers()
        self.wfile.write(result)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="session")
def wikidata_endpoint():
    """A local stand-in for Wikidata's SPARQL endpoint, so tests never use the network: it answers every query with the
    sample and keeps the queries it was sent."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SparqlEndpoint)
    server.queries = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield SimpleNamespace(url=f"http://127.0.0.1:{server.server_port}/sparql", queries=server.queries)
    server.shutdown()


@pytest.fixture(scope="session")
def upstream_built_dir(tmp_path_factory, mrds_zip, wikidata_endpoint) -> Path:
    """The repository's graph built once with snapshots of the MRDS and Wikidata samples, so it has source occurrences
    and upstream quantity values."""
    from capabilities.built import run_build
    from capabilities_pipeline.upstream import MRDS, WIKIDATA, fetch

    build_dir = tmp_path_factory.mktemp("upstream-build")
    fetch(MRDS, build_dir, mrds_zip(tmp_path_factory.mktemp("mrds-download")))
    fetch(WIKIDATA, build_dir, wikidata_endpoint.url, root=REPO_ROOT)
    run_build(REPO_ROOT, build_dir)
    return build_dir


@pytest.fixture
def data_copy(tmp_path: Path) -> Path:
    """A throwaway copy of the schemas and data, for tests that break files on purpose."""
    for directory in ("schema", "data", "examples"):
        shutil.copytree(REPO_ROOT / directory, tmp_path / directory)
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
