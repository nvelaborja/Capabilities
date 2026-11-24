"""Upstream datasets: downloading a snapshot of each, and loading it into the warehouse (ADR 0034, ADR 0041, ADR 0043).

A snapshot is the dataset as downloaded, converted to Parquet without changing a value, plus `snapshot.json`: where and
when it was retrieved, a hash of the download, and its license. Only Dagster downloads (`assets.py`); a build reads
whatever snapshots are already in the build directory, and loads an empty table for a dataset that has none, so the
graph still builds with no network.
"""

from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import yaml
from capabilities.built import SNAPSHOT_FILE, upstream_dir

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
class WikidataDataset(Dataset):
    """The result of a SPARQL query to Wikidata, as CSV. What is asked for comes from the curated layer: the items in
    the Wikidata crosswalk and the properties our quantities name (ADR 0043)."""

    def download(self, url: str, scratch: Path, root: Path) -> tuple[Path, Path, dict]:
        items, properties = crosswalked_items(root), quantity_properties(root)
        query = quantities_query(items, properties)
        download = scratch / "result.csv"
        request = urllib.request.Request(
            url,
            data=urllib.parse.urlencode({"query": query}).encode(),
            headers={"User-Agent": USER_AGENT, "Accept": "text/csv"},
        )
        save(request, download)
        return download, download, {"query": query, "items": len(items), "properties": sorted(properties)}


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

WIKIDATA = WikidataDataset(
    name="wikidata_quantities",
    url="https://query.wikidata.org/sparql",
    license="CC0 1.0 (Wikidata's structured data)",
    columns=("item", "property", "amount", "lower", "upper", "unit"),
)

DATASETS = (MRDS, WIKIDATA)


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


def crosswalked_items(root: Path) -> list[str]:
    """The Wikidata items our things are matched to (data/crosswalks/wikidata_things.csv)."""
    path = root / "data" / "crosswalks" / "wikidata_things.csv"
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as file:
        return sorted({row["wikidata"].strip() for row in csv.DictReader(file) if row["wikidata"].strip()})


def quantity_properties(root: Path) -> dict[str, str]:
    """Each Wikidata property our quantities name, and the quantity it holds."""
    properties = {}
    for path in sorted((root / "data" / "quantities").glob("*.yaml")):
        quantity = yaml.safe_load(path.read_text(encoding="utf-8"))
        if quantity.get("wikidata"):
            properties[quantity["wikidata"]] = quantity["id"]
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


def snapshot_of(dataset: Dataset, build_dir: Path) -> dict | None:
    path = dataset.directory(build_dir) / SNAPSHOT_FILE
    if not path.is_file() or not dataset.parquet(build_dir).is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_upstream(connection: duckdb.DuckDBPyConnection, build_dir: Path) -> dict[str, dict | None]:
    """Each dataset's snapshot into its raw table, or an empty table when there is no snapshot, and every snapshot's
    metadata into raw.upstream_snapshots (for provenance). Returns each dataset's snapshot metadata, or None."""
    connection.execute(
        "create or replace table raw.upstream_snapshots "
        "(dataset varchar, url varchar, retrieved_at timestamptz, sha256 varchar, row_count bigint, license varchar)"
    )
    snapshots = {}
    for dataset in DATASETS:
        snapshot = snapshots[dataset.name] = snapshot_of(dataset, build_dir)
        if snapshot:
            connection.execute(
                f"create or replace table {dataset.table} as select * from read_parquet(?)",
                [str(dataset.parquet(build_dir))],
            )
            connection.execute(
                "insert into raw.upstream_snapshots values (?, ?, ?, ?, ?, ?)",
                [dataset.name, snapshot["url"], snapshot["retrieved_at"], snapshot["sha256"], snapshot["rows"],
                 snapshot["license"]],
            )
        else:
            columns = ", ".join(f"{column} varchar" for column in dataset.columns)
            connection.execute(f"create or replace table {dataset.table} ({columns})")
    return snapshots


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()
