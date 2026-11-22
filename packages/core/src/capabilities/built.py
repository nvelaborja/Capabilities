"""Reading the built graph, the artifact the pipeline produces and the app reads (ADR 0038).

A build directory holds `graph/graph_nodes.parquet` (one row per node, its full document as JSON, and its provenance)
and `graph/manifest.json`, which records the fingerprint of the inputs it was built from. A build is current when
that fingerprint matches the inputs on disk now; otherwise the question commands and the server rebuild first.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

from .graph import Graph, LoadError

# Bump when the artifact's shape changes, so older builds are rebuilt rather than misread.
FORMAT_VERSION = 1
NODES_FILE = "graph_nodes.parquet"
MANIFEST_FILE = "manifest.json"

# Everything a build depends on: change any of these and the built graph is stale.
DATA_PATTERNS = ("data/**/*.yaml", "examples/**/*.yaml", "schema/*.json")
# The pipeline's own code and dbt project, found where the pipeline package is installed rather than under the data root.
CODE_PATTERNS = ("src/capabilities_pipeline/*.py", "dbt/**/*.sql", "dbt/**/*.yml")


def build_dir_for(root: Path, build_dir: Path | None = None) -> Path:
    """Where builds go: an explicit directory, then $CAPABILITIES_BUILD_DIR, then build/ in the repo."""
    if build_dir:
        return Path(build_dir).resolve()
    env = os.environ.get("CAPABILITIES_BUILD_DIR")
    return Path(env).resolve() if env else root / "build"


def graph_dir(build_dir: Path) -> Path:
    return build_dir / "graph"


def fingerprint(root: Path) -> str:
    """A hash of every input file's path and bytes (the data and the pipeline's code), plus the artifact format."""
    digest = hashlib.sha256(f"format {FORMAT_VERSION}\n".encode())
    add_files(digest, root, DATA_PATTERNS)
    pipeline = pipeline_root()
    if pipeline:
        add_files(digest, pipeline, CODE_PATTERNS)
    return digest.hexdigest()


def add_files(digest, base: Path, patterns: tuple[str, ...]) -> None:
    for path in sorted({path for pattern in patterns for path in base.glob(pattern) if path.is_file()}):
        digest.update(str(path.relative_to(base)).encode() + b"\0")
        digest.update(path.read_bytes() + b"\0")


def pipeline_root() -> Path | None:
    """The pipeline package's project directory (holding src/ and dbt/), if it is installed."""
    spec = importlib.util.find_spec("capabilities_pipeline")
    if not spec or not spec.origin:
        return None
    return Path(spec.origin).resolve().parents[2]


def read_manifest(build_dir: Path) -> dict | None:
    path = graph_dir(build_dir) / MANIFEST_FILE
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def is_current(root: Path, build_dir: Path) -> bool:
    manifest = read_manifest(build_dir)
    return bool(manifest) and manifest.get("fingerprint") == fingerprint(root) and (graph_dir(build_dir) / NODES_FILE).is_file()


def load_built(root: Path, build_dir: Path) -> Graph:
    """The graph from a build directory, without checking whether it is current."""
    import duckdb

    nodes = graph_dir(build_dir) / NODES_FILE
    if not nodes.is_file():
        raise LoadError(f"No built graph at {nodes}. Run `uv run capabilities build`.")
    rows = duckdb.sql(
        # Load order matters (it is the order lists come out in), so keep the order the inputs were read in.
        "select node_type, document::varchar, provenance::varchar from read_parquet(?) order by ordinal",
        params=[str(nodes)],
    ).fetchall()
    return Graph.from_documents(root, ((node_type, json.loads(document), provenance) for node_type, document, provenance in rows))


def current_graph(root: Path, build_dir: Path | None = None) -> Graph:
    """The built graph, rebuilt first if the inputs changed since the last build."""
    build_dir = build_dir_for(root, build_dir)
    if not is_current(root, build_dir):
        print("The built graph is missing or out of date; building it now…", file=sys.stderr)
        run_build(root, build_dir)
    return load_built(root, build_dir)


def run_build(root: Path, build_dir: Path) -> dict:
    try:
        from capabilities_pipeline.build import build
    except ImportError as exc:  # the core package can be installed alone
        raise LoadError("Building the graph needs the pipeline package. Run `uv sync` in the repository.") from exc
    return build(root, build_dir)
