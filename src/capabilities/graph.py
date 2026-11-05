"""Loading the YAML files into an in-memory graph with lookup indexes."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import yaml

# Which schema each top-level directory's files follow.
SCHEMA_BY_DIR = {
    "quantities": "quantity",
    "things": "thing",
    "verbs": "verb",
    "routes": "route",
    "profiles": "profile",
    "jobs": "job",
}

# Thing kinds and the subdirectory of data/things/ they live in.
THING_DIRS = {
    "materials": "material",
    "artifacts": "artifact",
    "techniques": "technique",
    "knowledge": "knowledge",
    "effects": "effect",
    "categories": "category",
}

PRECISION_QUANTITY = "tolerance_mm"


class LoadError(Exception):
    """The data could not be found or parsed."""


@dataclass(frozen=True)
class Document:
    path: Path
    schema: str
    data: dict


def find_root(start: Path | None = None) -> Path:
    """Locate the repository root that holds schema/ and data/."""
    env = os.environ.get("CAPABILITIES_ROOT")
    if env:
        return Path(env).resolve()
    origin = (start or Path.cwd()).resolve()
    for candidate in (origin, *origin.parents):
        if (candidate / "schema" / "route.schema.json").is_file() and (candidate / "data").is_dir():
            return candidate
    package_root = Path(__file__).resolve().parents[2]
    if (package_root / "data").is_dir():
        return package_root
    raise LoadError("Could not find the Capabilities data. Run from inside the repo, or set CAPABILITIES_ROOT.")


def data_files(root: Path) -> list[Path]:
    return sorted([*(root / "data").rglob("*.yaml"), *(root / "examples").rglob("*.yaml")])


def schema_for(root: Path, path: Path) -> str | None:
    for part in path.relative_to(root).parts:
        if part in SCHEMA_BY_DIR:
            return SCHEMA_BY_DIR[part]
    return None


def load_documents(root: Path) -> tuple[list[Document], list[str]]:
    """Parse every YAML file. Returns the documents plus a list of parse errors."""
    documents, errors = [], []
    for path in data_files(root):
        rel = path.relative_to(root)
        schema = schema_for(root, path)
        if schema is None:
            errors.append(f"{rel}: not inside a known data directory")
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            errors.append(f"{rel}: YAML parse error: {exc}")
            continue
        if not isinstance(data, dict):
            errors.append(f"{rel}: expected a mapping at the top level")
            continue
        documents.append(Document(path, schema, data))
    return documents, errors


@dataclass
class Graph:
    root: Path
    quantities: dict[str, dict] = field(default_factory=dict)
    things: dict[str, dict] = field(default_factory=dict)
    verbs: dict[str, dict] = field(default_factory=dict)
    routes: dict[str, dict] = field(default_factory=dict)
    profiles: dict[str, dict] = field(default_factory=dict)
    jobs: dict[str, dict] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.routes_achieving: dict[str, list[str]] = {}
        for route_id, route in self.routes.items():
            self.routes_achieving.setdefault(achieved_id(route), []).append(route_id)
        self._members: dict[str, frozenset[str]] = {}

    @classmethod
    def load(cls, root: Path | None = None) -> "Graph":
        root = root or find_root()
        documents, errors = load_documents(root)
        if errors:
            raise LoadError("\n".join(errors))
        buckets: dict[str, dict[str, dict]] = {schema: {} for schema in SCHEMA_BY_DIR.values()}
        for doc in documents:
            node_id = doc.data.get("id")
            if node_id in buckets[doc.schema]:
                raise LoadError(f"Duplicate id {node_id!r} in {doc.path.relative_to(root)}")
            buckets[doc.schema][node_id] = doc.data
        return cls(
            root,
            quantities=buckets["quantity"], things=buckets["thing"], verbs=buckets["verb"],
            routes=buckets["route"], profiles=buckets["profile"], jobs=buckets["job"],
        )

    # ------------------------------------------------------------------ lookups

    def kind(self, node_id: str) -> str | None:
        if node_id in self.things:
            return self.things[node_id]["kind"]
        if node_id in self.verbs:
            return "verb"
        if node_id in self.routes:
            return "route"
        return None

    def label(self, node_id: str) -> str:
        for bucket in (self.things, self.verbs, self.routes, self.profiles, self.jobs):
            if node_id in bucket:
                return bucket[node_id].get("label", node_id)
        return node_id

    def members(self, category: str) -> frozenset[str]:
        """All non-category things that belong to a category, directly or through sub-categories."""
        if category not in self._members:
            found: set[str] = set()
            for thing_id, thing in self.things.items():
                if category in thing.get("is_a", []):
                    if thing["kind"] == "category":
                        found |= self.members(thing_id)
                    else:
                        found.add(thing_id)
            self._members[category] = frozenset(found)
        return self._members[category]

    def is_free(self, thing_id: str) -> bool:
        """Ubiquitous natural materials are assumed available to everyone."""
        thing = self.things.get(thing_id, {})
        return thing.get("kind") == "material" and thing.get("origin") == "natural" and thing.get("availability") == "ubiquitous"

    def is_regional(self, thing_id: str) -> bool:
        return self.things.get(thing_id, {}).get("availability") == "regional"

    def bands(self, quantity: str) -> list[dict]:
        return self.quantities.get(quantity, {}).get("bands", [])

    def band(self, quantity: str, band_id: str) -> dict:
        for band in self.bands(quantity):
            if band["id"] == band_id:
                return band
        raise KeyError(f"Unknown band {band_id!r} for {quantity}")

    def band_of(self, quantity: str, value: float) -> str | None:
        for band in self.bands(quantity):
            low, high = band.get("min", float("-inf")), band.get("max", float("inf"))
            if low <= value < high:
                return band["id"]
        return None

    def precision_rank(self, band_id: str) -> int:
        """Position of a precision band from roughest (0) to finest."""
        ids = [band["id"] for band in self.bands(PRECISION_QUANTITY)]
        return ids.index(band_id)

    def verb_routes(self, verb: str, target: str | None) -> list[str]:
        """Routes that perform a verb and apply to the given target."""
        return [rid for rid in self.routes_achieving.get(verb, []) if self.applies_to(rid, target)]

    def applies_to(self, route_id: str, target: str | None) -> bool:
        allowed = self.routes[route_id].get("applies_to")
        if not allowed or target is None:
            return True
        return any(target == item or target in self.members(item) for item in allowed)

    def targets_for(self, verb: str) -> list[str]:
        kinds = set()
        for param in self.verbs[verb].get("params", {}).values():
            kinds |= set(param.get("kinds", []))
        return sorted(tid for tid, thing in self.things.items() if thing["kind"] in kinds)

    def thing_routes(self) -> Iterable[str]:
        return (rid for rid, route in self.routes.items() if "thing" in route["achieves"])


def achieved_id(route: dict) -> str:
    ((_, node_id),) = route["achieves"].items()
    return node_id


def achieved_kind(route: dict) -> str:
    ((kind, _),) = route["achieves"].items()
    return kind
