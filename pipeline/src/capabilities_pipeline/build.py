"""Build the graph: load the inputs into DuckDB, run the dbt project, and write the manifest (ADR 0038).

Extract and load happen here in Python; every transformation is a dbt model, so later inputs (upstream datasets,
ADR 0034) arrive as more raw tables and more models, not more Python.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import duckdb
from capabilities.built import (
    FACTS_FILE,
    FORMAT_VERSION,
    MANIFEST_FILE,
    NODES_FILE,
    OCCURRENCES_FILE,
    fingerprint,
    graph_dir,
)
from capabilities.graph import LoadError, load_documents

from .upstream import load_upstream

DBT_PROJECT = Path(__file__).resolve().parents[2] / "dbt"
WAREHOUSE_FILE = "warehouse.duckdb"


class BuildError(LoadError):
    """dbt failed: a model errored or a data test found a problem."""


def build(root: Path, build_dir: Path) -> dict:
    """Build the graph from the inputs under `root` into `build_dir`, and return the manifest.

    The same three steps are Dagster assets in `definitions.py`; this runs them in order without Dagster, which is
    what `capabilities build` and the automatic rebuild use.
    """
    load_inputs(root, build_dir)
    run_dbt(build_dir)
    return write_manifest(root, build_dir)


def write_manifest(root: Path, build_dir: Path) -> dict:
    """Record what the graph was built from. Written last: a build that failed part-way leaves no manifest that
    matches, so it is never read as current."""
    manifest = {
        "format_version": FORMAT_VERSION,
        # The inputs as they were when they were loaded, not as they are now: an edit made during the build must
        # leave the graph stale.
        "fingerprint": loaded_fingerprint(build_dir),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": git_commit(root),
        "tables": {name: row_count(graph_dir(build_dir) / name) for name in (NODES_FILE, FACTS_FILE, OCCURRENCES_FILE)},
        "upstream": loaded_snapshots(build_dir),
    }
    (graph_dir(build_dir) / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def load_inputs(root: Path, build_dir: Path) -> dict:
    """Every input into its raw table, and the inputs' fingerprint into raw.loads. Parsing them into columns is dbt's
    job. Returns how many curated documents, crosswalk rows and suppressions were loaded, and the snapshot of each
    upstream dataset used, with which copy (a download or the cold backup). Stops if a dataset has no copy (ADR 0044)."""
    # Taken before anything is read, so an edit made while loading leaves the graph stale.
    inputs = fingerprint(root, build_dir)
    graph_dir(build_dir).mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(build_dir / WAREHOUSE_FILE)) as connection:
        connection.execute("create schema if not exists raw")
        documents = load_curated_documents(connection, root)
        crosswalks = load_tables(connection, root / "data" / "crosswalks")
        suppressions = load_tables(connection, root / "data" / "suppressions")
        snapshots = load_upstream(connection, root, build_dir)
        connection.execute("create or replace table raw.loads (fingerprint varchar, loaded_at timestamptz)")
        connection.execute("insert into raw.loads values (?, now())", [inputs])
    return {"documents": documents, "crosswalks": crosswalks, "suppressions": suppressions, "upstream": snapshots}


def load_curated_documents(connection: duckdb.DuckDBPyConnection, root: Path) -> int:
    """Every curated document, whole, into raw.curated_documents, in the order it was read."""
    documents, errors = load_documents(root)
    if errors:
        raise LoadError("\n".join(errors))
    rows = [
        (ordinal, doc.schema, doc.data.get("id"), json.dumps(doc.data, ensure_ascii=False), str(doc.path.relative_to(root)))
        for ordinal, doc in enumerate(documents)
    ]
    connection.execute(
        "create or replace table raw.curated_documents "
        "(ordinal integer, node_type varchar, id varchar, document json, path varchar)"
    )
    connection.executemany("insert into raw.curated_documents values (?, ?, ?, ?, ?)", rows)
    return len(rows)


def load_tables(connection: duckdb.DuckDBPyConnection, directory: Path) -> dict[str, int]:
    """Each hand-kept table in `directory` (crosswalks and suppressions, ADR 0034) into raw.<its file name>, as text
    exactly as written. Not dbt seeds: a build reads its inputs from `root`, and dbt can't safely read seeds from outside
    its project (ADR 0041). Returns each table's number of rows."""
    rows = {}
    for path in sorted(directory.glob("*.csv")):
        connection.execute(
            f'create or replace table raw."{path.stem}" as select * from read_csv(?, header = true, all_varchar = true)',
            [str(path)],
        )
        rows[path.stem] = connection.execute(f'select count(*) from raw."{path.stem}"').fetchall()[0][0]
    return rows


def loaded_fingerprint(build_dir: Path) -> str:
    # Not read-only: dbt may still hold the file open in this process, and DuckDB refuses a second, differently
    # configured connection to it.
    with duckdb.connect(str(build_dir / WAREHOUSE_FILE)) as connection:
        return connection.execute("select fingerprint from raw.loads").fetchall()[0][0]


def loaded_snapshots(build_dir: Path) -> dict[str, dict]:
    """The upstream snapshots the graph was built from, as loaded (not as they are on disk now)."""
    with duckdb.connect(str(build_dir / WAREHOUSE_FILE)) as connection:
        rows = connection.execute(
            "select dataset, url, strftime(retrieved_at at time zone 'UTC', '%Y-%m-%dT%H:%M:%SZ'), sha256, row_count, "
            "license, copy from raw.upstream_snapshots order by dataset"
        ).fetchall()
    keys = ("url", "retrieved_at", "sha256", "rows", "license", "copy")
    return {dataset: dict(zip(keys, values)) for dataset, *values in rows}


def dbt_environment(build_dir: Path) -> None:
    """Point dbt at the build directory (profiles.yml reads it) and keep its logs out of the source tree."""
    os.environ["CAPABILITIES_BUILD_DIR"] = str(build_dir)
    os.environ["DBT_LOG_PATH"] = str(build_dir / "dbt" / "logs")
    # Dagster gives each run its own folder under this one.
    os.environ["DBT_TARGET_PATH"] = str(dbt_target_path(build_dir))
    # dbt's anonymous usage statistics are also off in dbt_project.yml; this covers older versions too.
    os.environ["DO_NOT_TRACK"] = "1"


def dbt_target_path(build_dir: Path) -> Path:
    return build_dir / "dbt" / "target"


def run_dbt(build_dir: Path) -> None:
    from dbt.cli.main import dbtRunner

    dbt_environment(build_dir)
    result = dbtRunner().invoke([
        "build",
        "--project-dir", str(DBT_PROJECT),
        "--profiles-dir", str(DBT_PROJECT),
        "--target-path", str(dbt_target_path(build_dir)),
        "--log-path", str(build_dir / "dbt" / "logs"),
        "--quiet",
    ])
    if not result.success:
        raise BuildError(f"dbt build failed: {failures(result)}. Details: {build_dir / 'dbt' / 'logs' / 'dbt.log'}")


def failures(result) -> str:
    if result.exception:
        return str(result.exception)
    failed = [f"{r.node.name} ({r.status})" for r in (result.result or []) if str(r.status) in ("error", "fail")]
    return ", ".join(failed) or "unknown error"


def row_count(parquet: Path) -> int:
    # count(id), not count(*): dbt-duckdb writes an empty table as one row of nulls, so that its columns keep their types.
    return duckdb.sql("select count(id) from read_parquet(?)", params=[str(parquet)]).fetchall()[0][0]


def git_commit(root: Path) -> str | None:
    try:
        output = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return output.stdout.strip() or None
