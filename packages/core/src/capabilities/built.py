"""Reading the built graph, the artifact the pipeline produces and the app reads (ADR 0038).

A build directory holds `graph/graph_nodes.parquet` (one row per node, its full document as JSON, and its provenance),
`graph/graph_facts.parquet` (where each quantity value comes from: upstream, curated or an override, ADR 0043),
`graph/curation_queue.parquet` (the gaps the build found, ADR 0045), `graph/source_occurrences.parquet` (where sources
are found, from upstream datasets, ADR 0036 and ADR 0041), `graph/reference_checks.parquet` (each cited work checked
against OpenAlex and Crossref, ADR 0047) and
`graph/manifest.json`, which records the fingerprint of the inputs it was built from. A build is current when
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
FORMAT_VERSION = 5
NODES_FILE = "graph_nodes.parquet"
FACTS_FILE = "graph_facts.parquet"
QUEUE_FILE = "curation_queue.parquet"
OCCURRENCES_FILE = "source_occurrences.parquet"
CHECKS_FILE = "reference_checks.parquet"
MANIFEST_FILE = "manifest.json"
SNAPSHOT_FILE = "snapshot.json"
# Cold backups of every upstream dataset, kept in git, so the graph builds offline or when a download fails (ADR 0044).
BACKUP_DIR = "snapshots"

# Everything a build depends on: change any of these and the built graph is stale.
DATA_PATTERNS = (
    "data/**/*.yaml", "data/**/*.csv", "examples/**/*.yaml", "schema/*.json", f"{BACKUP_DIR}/*/{SNAPSHOT_FILE}",
)
# Upstream snapshots, under the build directory: each dataset's snapshot.json changes whenever its data is downloaded again.
SNAPSHOT_PATTERNS = (f"*/{SNAPSHOT_FILE}",)
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


def upstream_dir(build_dir: Path) -> Path:
    """Where downloaded upstream snapshots are kept, one folder per dataset. A rebuild reads them; only Dagster downloads."""
    return build_dir / "upstream"


def fingerprint(root: Path, build_dir: Path | None = None) -> str:
    """A hash of every input file's path and bytes (the data, the upstream snapshots in `build_dir`, and the pipeline's
    code), plus the artifact format."""
    digest = hashlib.sha256(f"format {FORMAT_VERSION}\n".encode())
    add_files(digest, root, DATA_PATTERNS)
    if build_dir:
        add_files(digest, upstream_dir(build_dir), SNAPSHOT_PATTERNS)
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
    return bool(manifest) and manifest.get("fingerprint") == fingerprint(root, build_dir) and (graph_dir(build_dir) / NODES_FILE).is_file()


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
    graph = Graph.from_documents(root, ((node_type, json.loads(document), provenance) for node_type, document, provenance in rows))
    graph.facts = load_facts(build_dir)
    graph.reference_checks = load_reference_checks(build_dir)
    for _, document, provenance in rows:
        source = json.loads(provenance)
        if source.get("layer") == "upstream":
            graph.upstream_nodes[json.loads(document)["id"]] = source
    return graph


FACT_COLUMNS = ("id", "layer", "value", "curated_value", "upstream_value", "disagrees", "upstream", "override")
FACT_JSON = {"value", "curated_value", "upstream_value", "upstream", "override"}


def load_facts(build_dir: Path) -> dict[str, dict]:
    """Where each quantity value came from (ADR 0043), by fact id. Empty for a build without the facts table."""
    import duckdb

    path = graph_dir(build_dir) / FACTS_FILE
    if not path.is_file():
        return {}
    columns = ", ".join(f"{name}::varchar" if name in FACT_JSON else name for name in FACT_COLUMNS)
    rows = duckdb.sql(f"select {columns} from read_parquet(?) where id is not null", params=[str(path)]).fetchall()
    facts = {}
    for row in rows:
        fact = dict(zip(FACT_COLUMNS, row))
        facts[fact["id"]] = {key: json.loads(value) if key in FACT_JSON and value is not None else value
                             for key, value in fact.items()}
    return facts


CHECK_COLUMNS = (
    "citation", "result", "note", "match_service", "match_id", "match_doi", "match_title", "match_year", "free_copy",
    "links", "checked_at",
)


def load_reference_checks(build_dir: Path) -> dict[str, dict]:
    """Each cited work checked against OpenAlex and Crossref (ADR 0047), by citation. Empty for a build without them."""
    import duckdb

    path = graph_dir(build_dir) / CHECKS_FILE
    if not path.is_file():
        return {}
    columns = ", ".join(
        "links::varchar" if name == "links"
        else "strftime(checked_at at time zone 'UTC', '%Y-%m-%dT%H:%M:%SZ')" if name == "checked_at"
        else name
        for name in CHECK_COLUMNS
    )
    rows = duckdb.sql(f"select {columns} from read_parquet(?) where id is not null", params=[str(path)]).fetchall()
    checks = {}
    for row in rows:
        check = dict(zip(CHECK_COLUMNS, row))
        check["links"] = {link["url"]: link["state"] for link in json.loads(check["links"] or "[]")}
        checks[check["citation"]] = check
    return checks


# The occurrence columns the app uses. The geometry is left out: the longitude and latitude columns hold the same point,
# and reading them needs no spatial extension.
OCCURRENCE_COLUMNS = (
    "id", "source_id", "dataset", "record_id", "name", "longitude", "latitude", "country", "admin_area",
    "development_status", "deposit_type", "worked_by_year", "state", "attested_from", "attested_to", "periods",
    "approximate", "matched_on", "url",
)


def load_occurrences(build_dir: Path) -> list[dict]:
    """Where sources are found (ADR 0036, ADR 0041), one dictionary per occurrence, ordered by source and record."""
    import duckdb

    path = graph_dir(build_dir) / OCCURRENCES_FILE
    if not path.is_file():
        return []
    relation = duckdb.sql(
        # dbt-duckdb writes an empty table as one row of nulls, which `id is not null` skips.
        f"select {', '.join(OCCURRENCE_COLUMNS)} from read_parquet(?) where id is not null order by source_id, record_id",
        params=[str(path)],
    )
    return [dict(zip(OCCURRENCE_COLUMNS, row)) for row in relation.fetchall()]


def current_graph(root: Path, build_dir: Path | None = None) -> Graph:
    """The built graph, rebuilt first if the inputs changed since the last build."""
    build_dir = build_dir_for(root, build_dir)
    if not is_current(root, build_dir):
        print("The built graph is missing or out of date; building it now…", file=sys.stderr)
        run_build(root, build_dir)
    return load_built(root, build_dir)


QUEUE_COLUMNS = ("id", "kind", "subject", "label", "detail", "priority")


def load_queue(build_dir: Path) -> list[dict]:
    """The curation queue (ADR 0045): the gaps the build found, most valuable first within each kind."""
    import duckdb

    path = graph_dir(build_dir) / QUEUE_FILE
    if not path.is_file():
        return []
    rows = duckdb.sql(
        f"select {', '.join(QUEUE_COLUMNS)} from read_parquet(?) where id is not null "
        "order by kind <> 'reported', kind = 'unmatched_place', kind, priority desc nulls last, subject",
        params=[str(path)],
    ).fetchall()
    return [dict(zip(QUEUE_COLUMNS, row)) for row in rows]


def run_backup(root: Path, build_dir: Path) -> dict[str, dict | None]:
    """Make each downloaded snapshot its dataset's cold backup, when it is newer (ADR 0044). Returns, by dataset, the
    snapshot backed up, or None when the backup was already as new."""
    try:
        from capabilities_pipeline.upstream import DATASETS, back_up
    except ImportError as exc:  # the core package can be installed alone
        raise LoadError("Backing up snapshots needs the pipeline package. Run `uv sync` in the repository.") from exc
    return {dataset.name: back_up(dataset, root, build_dir) for dataset in DATASETS}


def run_build(root: Path, build_dir: Path) -> dict:
    try:
        from capabilities_pipeline.build import build
    except ImportError as exc:  # the core package can be installed alone
        raise LoadError("Building the graph needs the pipeline package. Run `uv sync` in the repository.") from exc
    return build(root, build_dir)
