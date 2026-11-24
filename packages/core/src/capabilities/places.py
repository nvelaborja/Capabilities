"""Where things are found: the occurrences of the sources a material comes from, shaped for the map (ADR 0036, ADR 0042).

Occurrences come from the built graph (`source_occurrences.parquet`, ADR 0041, ADR 0046). A material is found wherever
any of the sources it is extracted from is found; a source is found at its own occurrences. Some places belong to an ore
class rather than a source (a Pleiades copper mine doesn't say which ore was mined): a mineral extracted from the
ground is shown at its classes' places too, marked as such.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .graph import Graph

# The upstream datasets of places, and how each is named and linked in the app. Keys are the dataset names in the
# manifest.
DATASETS = {
    "mrds_deposits": {
        "id": "mrds",
        "label": "USGS Mineral Resources Data System (MRDS)",
        "short": "MRDS",
        "home": "https://mrdata.usgs.gov/mrds/",
        "note": "Modern records, most of them in the United States; a working year is the year production first began.",
    },
    "pleiades_places": {
        "id": "pleiades",
        "label": "Pleiades: a gazetteer of past places",
        "short": "Pleiades",
        "home": "https://pleiades.stoa.org",
        "note": "Ancient mines and quarries, with the periods they are attested in. CC BY 3.0. A copper, iron or tin "
        "mine doesn't say which ore was mined there.",
    },
}

# What each feature carries to the map: enough for its popup, and no more, since a material can have thousands.
FEATURE_PROPERTIES = (
    "id", "source_id", "dataset", "name", "country", "admin_area", "development_status", "deposit_type", "worked_by_year", "state",
    "attested_from", "attested_to", "periods", "approximate", "record_id", "url",
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
        if graph.things[thing_id].get("origin") == "extracted":
            sources += sorted(classes_with_places(graph, places, thing_id), key=graph.label)
    else:
        raise NotPlaceable(thing_id)
    return {
        "id": thing_id,
        "label": graph.label(thing_id),
        "kind": kind,
        "origin": graph.things[thing_id].get("origin"),
        "sources": [source_summary(graph, source, places.by_source.get(source, [])) for source in sources],
        "datasets": datasets(places.snapshots),
        "features": {
            "type": "FeatureCollection",
            "features": [
                feature(row, class_level=graph.kind(source) == "category")
                for source in sources for row in places.by_source.get(source, [])
            ],
        },
    }


def classes_with_places(graph: Graph, places: Places, thing_id: str) -> list[str]:
    """The classes the thing belongs to that have places of their own: where its kind of ore was mined, unrecorded
    which (ADR 0046)."""
    return [source for source in places.by_source if graph.kind(source) == "category" and thing_id in graph.members(source)]


def source_summary(graph: Graph, source: str, occurrences: list[dict]) -> dict:
    thing = graph.things[source]
    return {
        "id": source,
        "label": thing["label"],
        "availability": thing.get("availability"),
        "regions": thing.get("regions", []),
        "places": len(occurrences),
        "worked": sum(1 for row in occurrences if row["state"] == "worked"),
        # Places of the class, not of this source: which ore was mined there isn't recorded.
        "class_level": thing["kind"] == "category",
    }


def datasets(snapshots: dict[str, dict]) -> list[dict]:
    """The upstream snapshots of places loaded into the build, with when they were retrieved. Datasets of other facts
    (Wikidata's quantities) are left out: they put nothing on the map."""
    return [
        {**DATASETS[name], "retrieved_at": snapshot.get("retrieved_at"), "license": snapshot.get("license")}
        for name, snapshot in sorted(snapshots.items())
        if name in DATASETS
    ]


def feature(row: dict, class_level: bool = False) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [row["longitude"], row["latitude"]]},
        "properties": {**{key: row[key] for key in FEATURE_PROPERTIES}, "class_level": class_level},
    }
