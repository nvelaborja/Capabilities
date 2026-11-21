"""Build the graph: load the curated layer into DuckDB, run the dbt project, and write the manifest (ADR 0038).

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
from capabilities.built import FORMAT_VERSION, MANIFEST_FILE, NODES_FILE, fingerprint, graph_dir
from capabilities.graph import LoadError, load_documents

DBT_PROJECT = Path(__file__).resolve().parents[2] / "dbt"
WAREHOUSE_FILE = "warehouse.duckdb"


class BuildError(LoadError):
    """dbt failed: a model errored or a data test found a problem."""


def build(root: Path, build_dir: Path) -> dict:
    """Build the graph from the inputs under `root` into `build_dir`, and return the manifest."""
    inputs = fingerprint(root)
    graph_dir(build_dir).mkdir(parents=True, exist_ok=True)
    warehouse = build_dir / WAREHOUSE_FILE
    load_curated(root, warehouse)
    run_dbt(build_dir)
    manifest = {
        "format_version": FORMAT_VERSION,
        "fingerprint": inputs,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": git_commit(root),
        "tables": {NODES_FILE: row_count(graph_dir(build_dir) / NODES_FILE)},
    }
    # Written last: a build that failed part-way leaves no manifest that matches, so it is never read as current.
    (graph_dir(build_dir) / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def load_curated(root: Path, warehouse: Path) -> None:
    """Every curated document, whole, into raw.curated_documents. Parsing it into columns is dbt's job."""
    documents, errors = load_documents(root)
    if errors:
        raise LoadError("\n".join(errors))
    rows = [
        (ordinal, doc.schema, doc.data.get("id"), json.dumps(doc.data, ensure_ascii=False), str(doc.path.relative_to(root)))
        for ordinal, doc in enumerate(documents)
    ]
    with duckdb.connect(str(warehouse)) as connection:
        connection.execute("create schema if not exists raw")
        connection.execute(
            "create or replace table raw.curated_documents "
            "(ordinal integer, node_type varchar, id varchar, document json, path varchar)"
        )
        connection.executemany("insert into raw.curated_documents values (?, ?, ?, ?, ?)", rows)


def run_dbt(build_dir: Path) -> None:
    from dbt.cli.main import dbtRunner

    # dbt's anonymous usage statistics are also off in dbt_project.yml; this covers older versions too.
    os.environ["DO_NOT_TRACK"] = "1"
    os.environ["CAPABILITIES_BUILD_DIR"] = str(build_dir)
    result = dbtRunner().invoke([
        "build",
        "--project-dir", str(DBT_PROJECT),
        "--profiles-dir", str(DBT_PROJECT),
        "--target-path", str(build_dir / "dbt" / "target"),
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
    return duckdb.sql("select count(*) from read_parquet(?)", params=[str(parquet)]).fetchall()[0][0]


def git_commit(root: Path) -> str | None:
    try:
        output = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return output.stdout.strip() or None
