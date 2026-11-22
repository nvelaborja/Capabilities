"""Where things are found: the occurrences of the sources a material comes from, shaped for the map (ADR 0036, ADR 0042).

Occurrences come from the built graph (`source_occurrences.parquet`, ADR 0041). A material is found wherever any of
the sources it is extracted from is found; a source is found at its own occurrences.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .graph import Graph

# How each upstream snapshot is named and linked in the app. Keys are the dataset names in the manifest.
DATASETS = {
    "mrds_deposits": {
        "id": "mrds",
        "label": "USGS Mineral Resources Data System (MRDS)",
        "home": "https://mrdata.usgs.gov/mrds/",
    },
}

# What each feature carries to the map: enough for its popup, and no more, since a material can have thousands.
FEATURE_PROPERTIES = (
    "id", "source_id", "name", "country", "admin_area", "development_status", "deposit_type", "worked_by_year", "state",
    "record_id", "url",
)


class NotPlaceable(Exception):
    """The id is not a material or a source, so it has no places."""


@dataclass
class Places:
    """Every occurrence, grouped by source kind, and the upstream snapshots they came from."""

    by_source: dict[str, list[dict]] = field(default_factory=dict)
    snapshots: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def from_rows(cls, rows: list[dict], snapshots: dict[str, dict] | None = None) -> "Places":
        grouped: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            grouped[row["source_id"]].append(row)
        return cls(dict(grouped), snapshots or {})


def places_view(graph: Graph, places: Places, thing_id: str) -> dict:
    """Where a material or source is found: a summary of each source, the datasets, and every place as GeoJSON."""
    kind = graph.kind(thing_id)
    if kind == "source":
        sources = [thing_id]
    elif kind == "material":
        sources = sorted(graph.sources_of(thing_id), key=graph.label)
    else:
        raise NotPlaceable(thing_id)
    occurrences = [row for source in sources for row in places.by_source.get(source, [])]
    return {
        "id": thing_id,
        "label": graph.label(thing_id),
        "kind": kind,
        "origin": graph.things[thing_id].get("origin"),
        "sources": [source_summary(graph, source, places.by_source.get(source, [])) for source in sources],
        "datasets": datasets(places.snapshots),
        "features": {"type": "FeatureCollection", "features": [feature(row) for row in occurrences]},
    }


def source_summary(graph: Graph, source: str, occurrences: list[dict]) -> dict:
    thing = graph.things[source]
    return {
        "id": source,
        "label": thing["label"],
        "availability": thing.get("availability"),
        "regions": thing.get("regions", []),
        "places": len(occurrences),
        "worked": sum(1 for row in occurrences if row["state"] == "worked"),
    }


def datasets(snapshots: dict[str, dict]) -> list[dict]:
    """The upstream snapshots loaded into the build, with when they were retrieved."""
    known = []
    for name, snapshot in sorted(snapshots.items()):
        about = DATASETS.get(name, {"id": name, "label": name, "home": snapshot.get("url")})
        known.append({**about, "retrieved_at": snapshot.get("retrieved_at"), "license": snapshot.get("license")})
    return known


def feature(row: dict) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [row["longitude"], row["latitude"]]},
        "properties": {key: row[key] for key in FEATURE_PROPERTIES},
    }
