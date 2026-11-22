"""Upstream datasets: downloading a snapshot of each, and loading it into the warehouse (ADR 0034, ADR 0041).

A snapshot is the dataset as downloaded, converted to Parquet without changing a value, plus `snapshot.json`: where and
when it was retrieved, a hash of the download, and its license. Only Dagster downloads (`assets.py`); a build reads
whatever snapshots are already in the build directory, and loads an empty table for a dataset that has none, so the
graph still builds with no network.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import duckdb
from capabilities.built import SNAPSHOT_FILE, upstream_dir


@dataclass(frozen=True)
class Dataset:
    name: str
    url: str
    member: str  # the file inside the downloaded zip
    license: str
    columns: tuple[str, ...]  # every column, kept as text: typing and cleaning are dbt's job

    @property
    def table(self) -> str:
        return f"raw.{self.name}"

    def directory(self, build_dir: Path) -> Path:
        return upstream_dir(build_dir) / self.name

    def parquet(self, build_dir: Path) -> Path:
        return self.directory(build_dir) / f"{self.name}.parquet"


MRDS = Dataset(
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

DATASETS = (MRDS,)

# Some servers (USGS among them) refuse Python's default user agent. This one is deliberately generic.
USER_AGENT = "dataset-snapshot/1.0"


def fetch(dataset: Dataset, build_dir: Path, url: str | None = None) -> dict:
    """Download the dataset, convert it to Parquet, and record the snapshot. Returns the snapshot's metadata."""
    url = url or dataset.url
    directory = dataset.directory(build_dir)
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directory) as scratch:
        download = Path(scratch) / "download.zip"
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request) as response, download.open("wb") as out:
            headers = response.headers
            while chunk := response.read(1 << 20):
                out.write(chunk)
        with zipfile.ZipFile(download) as archive:
            csv = Path(archive.extract(dataset.member, scratch))
        converted = Path(scratch) / "converted.parquet"
        rows = to_parquet(dataset, csv, converted)
        converted.replace(dataset.parquet(build_dir))
        snapshot = {
            "dataset": dataset.name,
            "url": url,
            "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "last_modified": headers.get("Last-Modified"),
            "sha256": sha256(download),
            "rows": rows,
            "license": dataset.license,
        }
    # Written last, and it is what the build's fingerprint reads: a download that failed part-way changes nothing.
    (directory / SNAPSHOT_FILE).write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    return snapshot


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
