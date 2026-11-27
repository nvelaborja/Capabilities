"""Upstream datasets: downloading a snapshot of each, and loading it into the warehouse (ADR 0034, ADR 0041, ADR 0043).

A snapshot is the dataset as downloaded, converted to Parquet without changing a value, plus `snapshot.json`: where and
when it was retrieved, a hash of the download, and its license. Only Dagster downloads (`assets.py`), into
build/upstream/. Every dataset is required (ADR 0044): a build uses the newest copy of each, the latest download or the
cold backup kept in git under snapshots/, and stops if a dataset has neither. `capabilities backup` makes the latest
downloads the cold backups.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import yaml
from capabilities.built import BACKUP_DIR, SNAPSHOT_FILE, upstream_dir
from capabilities.graph import LoadError

from .citations import COLUMNS as REFERENCE_COLUMNS
from .citations import Lookups, cited_works, write_rows

# Some servers (USGS among them) refuse Python's default user agent. This one is deliberately generic.
USER_AGENT = "dataset-snapshot/1.0"
TIMEOUT_S = 300


@dataclass(frozen=True)
class Dataset:
    name: str
    url: str
    license: str
    columns: tuple[str, ...]  # every column, kept as text: typing and cleaning are dbt's job

    @property
    def table(self) -> str:
        return f"raw.{self.name}"

    def directory(self, build_dir: Path) -> Path:
        return upstream_dir(build_dir) / self.name

    def parquet(self, build_dir: Path) -> Path:
        return self.directory(build_dir) / f"{self.name}.parquet"

    def download(self, url: str, scratch: Path, root: Path) -> tuple[Path, Path, dict]:
        """Download into `scratch`. Returns the file as downloaded (to hash), the CSV in it, and what else the
        snapshot should record."""
        raise NotImplementedError


@dataclass(frozen=True)
class ZipDataset(Dataset):
    """A CSV published inside a zip file."""

    member: str = ""  # the file inside the downloaded zip

    def download(self, url: str, scratch: Path, root: Path) -> tuple[Path, Path, dict]:
        download = scratch / "download.zip"
        headers = save(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), download)
        with zipfile.ZipFile(download) as archive:
            extracted = Path(archive.extract(self.member, scratch))
        return download, extracted, {"last_modified": headers.get("Last-Modified")}


@dataclass(frozen=True)
class GzipCsvDataset(Dataset):
    """A CSV published compressed with gzip."""

    def download(self, url: str, scratch: Path, root: Path) -> tuple[Path, Path, dict]:
        download = scratch / "download.csv.gz"
        headers = save(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), download)
        # DuckDB reads the gzip directly, so the file hashed is the file converted.
        return download, download, {"last_modified": headers.get("Last-Modified")}


@dataclass(frozen=True)
class WikidataDataset(Dataset):
    """The result of a SPARQL query to Wikidata, as CSV. What is asked for comes from the curated layer: the items in
    the Wikidata crosswalks, and for quantities the properties our quantities name (ADR 0043, ADR 0045)."""

    def query(self, root: Path) -> tuple[str, dict]:
        """The query, and what the snapshot should record about it."""
        raise NotImplementedError

    def download(self, url: str, scratch: Path, root: Path) -> tuple[Path, Path, dict]:
        query, about = self.query(root)
        download = scratch / "result.csv"
        request = urllib.request.Request(
            url,
            data=urllib.parse.urlencode({"query": query}).encode(),
            headers={"User-Agent": USER_AGENT, "Accept": "text/csv"},
        )
        save(request, download)
        return download, download, {"query": query, **about}


@dataclass(frozen=True)
class WikidataQuantities(WikidataDataset):
    """Each crosswalked item's best-ranked statements of the properties our quantities name."""

    def query(self, root: Path) -> tuple[str, dict]:
        items, properties = crosswalked_items(root), quantity_properties(root)
        return quantities_query(items, properties), {"items": len(items), "properties": sorted(properties)}


@dataclass(frozen=True)
class WikidataItems(WikidataDataset):
    """Each crosswalked item's English label and description, and its chemical formula (P274): what an upstream node
    is called and described with (ADR 0045)."""

    def query(self, root: Path) -> tuple[str, dict]:
        items = crosswalked_items(root)
        return items_query(items), {"items": len(items)}


@dataclass(frozen=True)
class ReferenceCandidates(Dataset):
    """What OpenAlex and Crossref hold for each work the curated layer cites, and whether each cited link still loads
    (ADR 0047). `url` is OpenAlex's API; Crossref's is `crossref_url`."""

    crossref_url: str = ""

    def download(self, url: str, scratch: Path, root: Path) -> tuple[Path, Path, dict]:
        works = cited_works(root)
        lookups = Lookups(url, self.crossref_url, USER_AGENT)
        for work in works:
            lookups.work(work)
        for link in sorted({url for work in works for url in work.urls}):
            lookups.link(link)
        download = scratch / "candidates.csv"
        write_rows(lookups.rows, download)
        return download, download, {
            "crossref_url": self.crossref_url,
            "works": len(works),
            "searched": sum(work.searchable for work in works),
        }


# The fields of the report form (.github/ISSUE_TEMPLATE/report.yml), by the heading GitHub gives each in the issue.
REPORT_FIELDS = {"Fact": "fact", "Kind": "kind", "Reference": "reference", "Agent run": "run"}
REPORT_WRITTEN = "What is wrong"  # the first field the reader writes, after all of the app's
REPORT_PAGES = 10  # of 100 issues each: far more open reports than anyone would leave unread


@dataclass(frozen=True)
class GitHubReports(Dataset):
    """The repository's open issues labelled `report`: what readers reported from the app's detail pane (ADR 0050).
    Only what the queue needs is kept: the issue, its title, and the fields the app filled in. Not who reported it, nor
    what they wrote, which stay on GitHub."""

    def download(self, url: str, scratch: Path, root: Path) -> tuple[Path, Path, dict]:
        rows = []
        for page in range(1, REPORT_PAGES + 1):
            query = urllib.parse.urlencode({"labels": "report", "state": "open", "per_page": 100, "page": page})
            request = urllib.request.Request(f"{url}?{query}", headers={
                "User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                issues = json.load(response)
            # The issues API lists pull requests too; a report is an issue.
            rows += [report_row(issue) for issue in issues if "pull_request" not in issue]
            if len(issues) < 100:
                break
        download = scratch / "reports.csv"
        with download.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=self.columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        return download, download, {"label": "report", "state": "open"}


def report_row(issue: dict) -> dict:
    fields = report_fields(issue.get("body") or "")
    return {"number": str(issue["number"]), "url": issue["html_url"], "title": issue["title"],
            "created_at": issue["created_at"], **{column: fields.get(column, "") for column in REPORT_FIELDS.values()}}


def report_fields(body: str) -> dict[str, str]:
    """The form's fields from an issue's body, which GitHub writes as `### <label>` followed by the answer, or by
    "_No response_" for one left empty. Only the fields before what the reader writes are read: a "### Fact" they type
    there mustn't replace the fact the app filled in."""
    fields = {}
    for heading, answer in re.findall(r"^### (.+?)\s*\n(.*?)(?=^### |\Z)", body, re.MULTILINE | re.DOTALL):
        if heading.strip() == REPORT_WRITTEN:
            break
        column = REPORT_FIELDS.get(heading.strip())
        if column and (value := answer.strip()) != "_No response_":
            fields[column] = value
    return fields


MRDS = ZipDataset(
    name="mrds_deposits",
    url="https://mrdata.usgs.gov/mrds/mrds-csv.zip",
    member="mrds.csv",
    license="US public domain (a work of the U.S. Geological Survey)",
    columns=(
        "dep_id", "url", "mrds_id", "mas_id", "site_name", "latitude", "longitude", "region", "country", "state",
        "county", "com_type", "commod1", "commod2", "commod3", "oper_type", "dep_type", "prod_size", "dev_stat", "ore",
        "gangue", "other_matl", "orebody_fm", "work_type", "model", "alteration", "conc_proc", "names", "ore_ctrl",
        "reporter", "hrock_unit", "hrock_type", "arock_unit", "arock_type", "structure", "tectonic", "ref", "yfp_ba",
        "yr_fst_prd", "ylp_ba", "yr_lst_prd", "dy_ba", "disc_yr", "prod_yrs", "discr", "score",
    ),
)

WIKIDATA = WikidataQuantities(
    name="wikidata_quantities",
    url="https://query.wikidata.org/sparql",
    license="CC0 1.0 (Wikidata's structured data)",
    columns=("item", "property", "amount", "lower", "upper", "unit"),
)

WIKIDATA_ITEMS = WikidataItems(
    name="wikidata_items",
    url="https://query.wikidata.org/sparql",
    license="CC0 1.0 (Wikidata's structured data)",
    columns=("item", "label", "description", "formula"),
)

PLEIADES = GzipCsvDataset(
    name="pleiades_places",
    url="https://atlantides.org/downloads/pleiades/dumps/pleiades-places-latest.csv.gz",
    license="CC BY 3.0 (Pleiades: a gazetteer of past places, https://pleiades.stoa.org)",
    columns=(
        "authors", "bbox", "connectsWith", "created", "creators", "currentVersion", "description", "extent",
        "featureTypes", "geoContext", "hasConnectionsWith", "id", "locationPrecision", "maxDate", "minDate", "modified",
        "path", "reprLat", "reprLatLong", "reprLong", "tags", "timePeriods", "timePeriodsKeys", "timePeriodsRange",
        "title", "uid",
    ),
)

REFERENCES = ReferenceCandidates(
    name="reference_candidates",
    url="https://api.openalex.org",
    crossref_url="https://api.crossref.org",
    license="CC0 1.0 (OpenAlex); Crossref's bibliographic metadata, which has no restrictions (no abstracts are kept)",
    columns=REFERENCE_COLUMNS,
)

REPORTS = GitHubReports(
    name="github_reports",
    url="https://api.github.com/repos/nvelaborja/Capabilities/issues",
    license="The project's own issue tracker; only issue numbers, titles and the fields the app filled in are kept",
    columns=("number", "url", "title", "created_at", *REPORT_FIELDS.values()),
)

DATASETS = (MRDS, WIKIDATA, WIKIDATA_ITEMS, PLEIADES, REFERENCES, REPORTS)


def fetch(dataset: Dataset, build_dir: Path, url: str | None = None, root: Path | None = None) -> dict:
    """Download the dataset, convert it to Parquet, and record the snapshot. Returns the snapshot's metadata. `root`
    is the data the query is built from, for a dataset that asks for what the curated layer names."""
    url = url or dataset.url
    directory = dataset.directory(build_dir)
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directory) as scratch:
        download, csv_file, extra = dataset.download(url, Path(scratch), root or Path.cwd())
        converted = Path(scratch) / "converted.parquet"
        rows = to_parquet(dataset, csv_file, converted)
        converted.replace(dataset.parquet(build_dir))
        snapshot = {
            "dataset": dataset.name,
            "url": url,
            "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sha256": sha256(download),
            "rows": rows,
            "license": dataset.license,
            **extra,
        }
    # Written last, and it is what the build's fingerprint reads: a download that failed part-way changes nothing.
    (directory / SNAPSHOT_FILE).write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    return snapshot


def save(request: urllib.request.Request, path: Path):
    """Stream a response to a file; returns its headers."""
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response, path.open("wb") as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)
        return response.headers


# The crosswalks that match our things to Wikidata items: curated things (ADR 0043), and the ore minerals that become
# upstream nodes (ADR 0045).
WIKIDATA_CROSSWALKS = ("wikidata_things.csv", "ore_minerals.csv")


def crosswalked_items(root: Path) -> list[str]:
    """Every Wikidata item a crosswalk names. Rows marked as reviewed and rejected (class none) are left out: nothing in
    the graph is built from them."""
    items = set()
    for name in WIKIDATA_CROSSWALKS:
        path = root / "data" / "crosswalks" / name
        if not path.is_file():
            continue
        with path.open(newline="", encoding="utf-8") as file:
            items |= {
                row["wikidata"].strip() for row in csv.DictReader(file)
                if row["wikidata"].strip() and row.get("class") != "none"
            }
    return sorted(items)


def items_query(items: list[str]) -> str:
    """SPARQL for each item's English label and description, and its chemical formulas (one row per formula)."""
    if not items:
        raise ValueError("Nothing to ask Wikidata: no crosswalked items.")
    values = " ".join(f"wd:{item}" for item in items)
    return f"""SELECT (STRAFTER(STR(?entity), "/entity/") AS ?item) ?label ?description ?formula
WHERE {{
  VALUES ?entity {{ {values} }}
  OPTIONAL {{ ?entity rdfs:label ?label . FILTER(LANG(?label) = "en") }}
  OPTIONAL {{ ?entity schema:description ?description . FILTER(LANG(?description) = "en") }}
  OPTIONAL {{ ?entity wdt:P274 ?formula }}
}}
ORDER BY ?item ?formula"""


def quantity_properties(root: Path) -> dict[str, str]:
    """Each Wikidata property our quantities name, and the quantity it holds."""
    properties = {}
    for path in sorted((root / "data" / "quantities").glob("*.yaml")):
        quantity = yaml.safe_load(path.read_text(encoding="utf-8"))
        if quantity.get("wikidata"):
            properties[quantity["wikidata"]["property"]] = quantity["id"]
    return properties


def quantities_query(items: list[str], properties: dict[str, str]) -> str:
    """SPARQL for the quantity statements of the given items: one row per statement, with its bounds and unit. Only
    each property's best-ranked statements, which is what Wikidata itself treats as current."""
    if not items or not properties:
        raise ValueError("Nothing to ask Wikidata: no crosswalked items, or no quantity names a Wikidata property.")
    values = " ".join(f"wd:{item}" for item in items)
    patterns = " UNION ".join(
        f'{{ ?entity p:{prop} ?statement . ?statement psv:{prop} ?value . BIND("{prop}" AS ?property) }}'
        for prop in sorted(properties)
    )
    return f"""SELECT (STRAFTER(STR(?entity), "/entity/") AS ?item) ?property ?amount ?lower ?upper
       (STRAFTER(STR(?unitEntity), "/entity/") AS ?unit)
WHERE {{
  VALUES ?entity {{ {values} }}
  {patterns}
  ?statement a wikibase:BestRank .
  ?value wikibase:quantityAmount ?amount ; wikibase:quantityUnit ?unitEntity .
  OPTIONAL {{ ?value wikibase:quantityLowerBound ?lower }}
  OPTIONAL {{ ?value wikibase:quantityUpperBound ?upper }}
}}
ORDER BY ?item ?property ?amount"""


def to_parquet(dataset: Dataset, csv: Path, parquet: Path) -> int:
    """Every row and column as text, exactly as published."""
    with duckdb.connect() as connection:
        relation = connection.read_csv(str(csv), header=True, all_varchar=True)
        if tuple(relation.columns) != dataset.columns:
            raise ValueError(f"{dataset.name}: the published columns changed: {relation.columns}")
        relation.write_parquet(str(parquet))
        return connection.execute("select count(*) from read_parquet(?)", [str(parquet)]).fetchall()[0][0]


class MissingSnapshot(LoadError):
    """A dataset has neither a download nor a cold backup: the graph can't be built without it (ADR 0044)."""


@dataclass(frozen=True)
class Copy:
    """One copy of a dataset's snapshot: where it is, which kind it is, and its snapshot.json."""

    dataset: Dataset
    directory: Path
    kind: str  # "download" (build/upstream/) or "backup" (snapshots/ in the repository)
    snapshot: dict

    @property
    def parquet(self) -> Path:
        return self.directory / f"{self.dataset.name}.parquet"


def backup_directory(dataset: Dataset, root: Path) -> Path:
    """Where the dataset's cold backup is kept: snapshots/<dataset>/ in the repository, in git."""
    return root / BACKUP_DIR / dataset.name


def copy_in(dataset: Dataset, directory: Path, kind: str) -> Copy | None:
    path = directory / SNAPSHOT_FILE
    if not path.is_file() or not (directory / f"{dataset.name}.parquet").is_file():
        return None
    return Copy(dataset, directory, kind, json.loads(path.read_text(encoding="utf-8")))


def snapshot_of(dataset: Dataset, build_dir: Path) -> dict | None:
    """The downloaded snapshot in the build directory, if there is one."""
    copy = copy_in(dataset, dataset.directory(build_dir), "download")
    return copy.snapshot if copy else None


def best_copy(dataset: Dataset, root: Path, build_dir: Path) -> Copy | None:
    """The newest copy of the dataset: the latest download, or the cold backup when it is newer or there is no
    download (offline, or a download that failed)."""
    copies = [
        copy for copy in (
            copy_in(dataset, dataset.directory(build_dir), "download"),
            copy_in(dataset, backup_directory(dataset, root), "backup"),
        ) if copy
    ]
    return max(copies, key=lambda copy: copy.snapshot["retrieved_at"], default=None)


def load_upstream(connection: duckdb.DuckDBPyConnection, root: Path, build_dir: Path) -> dict[str, dict]:
    """Each dataset's newest copy into its raw table, and every snapshot's metadata into raw.upstream_snapshots (for
    provenance). Every dataset is required: with no copy of one, nothing is loaded and the build stops (ADR 0044).
    Returns each dataset's snapshot metadata, with which copy was used."""
    copies = {dataset.name: best_copy(dataset, root, build_dir) for dataset in DATASETS}
    missing = [name for name, copy in copies.items() if copy is None]
    if missing:
        raise MissingSnapshot(
            "No copy of " + ", ".join(missing) + ": every upstream dataset is required. Download it "
            + " or ".join(f"(`cd pipeline && uv run dg launch --assets 'upstream/{name}'`)" for name in missing)
            + f", or restore its cold backup in {BACKUP_DIR}/ from git."
        )
    connection.execute(
        "create or replace table raw.upstream_snapshots (dataset varchar, url varchar, retrieved_at timestamptz, "
        "sha256 varchar, row_count bigint, license varchar, copy varchar)"
    )
    for copy in copies.values():
        connection.execute(
            f"create or replace table {copy.dataset.table} as select * from read_parquet(?)", [str(copy.parquet)]
        )
        snapshot = copy.snapshot
        connection.execute(
            "insert into raw.upstream_snapshots values (?, ?, ?, ?, ?, ?, ?)",
            [copy.dataset.name, snapshot["url"], snapshot["retrieved_at"], snapshot["sha256"], snapshot["rows"],
             snapshot["license"], copy.kind],
        )
    return {name: {**copy.snapshot, "copy": copy.kind} for name, copy in copies.items()}


def back_up(dataset: Dataset, root: Path, build_dir: Path) -> dict | None:
    """Make the downloaded snapshot the dataset's cold backup, when it is newer than the backup. The Parquet is
    rewritten with stronger compression; every value, and the snapshot's record of the download, stay the same.
    Returns the snapshot backed up, or None when there was nothing newer to back up."""
    download = copy_in(dataset, dataset.directory(build_dir), "download")
    backup = copy_in(dataset, backup_directory(dataset, root), "backup")
    if download is None or (backup and backup.snapshot["retrieved_at"] >= download.snapshot["retrieved_at"]):
        return None
    directory = backup_directory(dataset, root)
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directory) as scratch:
        compressed = Path(scratch) / "backup.parquet"
        with duckdb.connect() as connection:
            connection.execute(
                f"copy (select * from read_parquet(?)) to '{compressed}' (format parquet, compression zstd, "
                "compression_level 19)",
                [str(download.parquet)],
            )
        compressed.replace(directory / f"{dataset.name}.parquet")
    # Written last, as with a download: a backup that failed part-way leaves the old snapshot.json in place.
    (directory / SNAPSHOT_FILE).write_text(json.dumps(download.snapshot, indent=2) + "\n", encoding="utf-8")
    return download.snapshot


def fetch_or_fall_back(dataset: Dataset, root: Path, build_dir: Path, url: str | None = None) -> tuple[dict, str | None]:
    """Download the dataset; if the network fails (offline, or the server is down) and there is a cold backup, use
    that instead. Returns the snapshot the build will use, and the error that made it fall back, if any. Any other
    failure, such as changed columns, is raised: that needs a change to the code, not a backup."""
    try:
        return fetch(dataset, build_dir, url, root=root), None
    except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
        backup = copy_in(dataset, backup_directory(dataset, root), "backup")
        if backup is None:
            raise
        return {**backup.snapshot, "copy": "backup"}, str(error)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()
