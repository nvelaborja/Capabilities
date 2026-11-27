"""Profiles in space and time (ADR 0036, ADR 0052): a profile with a place and years has an area, from Cliopatria's
borders, and the sources found inside it.

A source found inside, worked by the profile's last year, counts as had: it joins the profile's selection as though it
were listed. One found inside but not known to have been worked by then is a "maybe": it is shown, never assumed, and
can be added by hand. The hand-picked list still wins: a listed source is had wherever the map puts it. Only sources
can be had: an ore class found inside (a mine that doesn't say which ore) is shown, but a route takes from a source.
"""

from __future__ import annotations

from .graph import Graph
from .reasoner import Selection


def sources_from_map(graph: Graph, profile_id: str) -> frozenset[str]:
    """The sources a profile had because the map puts one of their workings inside its area, by its last year."""
    place = graph.profile_places.get(profile_id)
    if not place:
        return frozenset()
    return frozenset(
        source["source_id"] for source in place["sources"]
        if source["availability"] == "yes" and graph.kind(source["source_id"]) == "source"
    )


def profile_selection(graph: Graph, profile_id: str) -> Selection:
    """What a profile starts with: its list, and the sources it had from the map."""
    return Selection.from_profile(graph.profiles[profile_id]) | Selection(sources_from_map(graph, profile_id))


def added_by_map(graph: Graph, profile_id: str) -> list[str]:
    """The sources the map adds to a profile that its list doesn't already name."""
    listed = Selection.from_profile(graph.profiles[profile_id]).things
    return sorted(sources_from_map(graph, profile_id) - listed)


def profile_view(graph: Graph, profile_id: str) -> dict:
    """A profile as the app shows it: the curated document, and its place, if it has one."""
    return {**graph.profiles[profile_id], "map": place_view(graph, profile_id)}


def place_view(graph: Graph, profile_id: str) -> dict | None:
    """The profile's area and the sources inside it, had first, each with how many of its places were worked by then."""
    place = graph.profile_places.get(profile_id)
    if not place:
        return None
    listed = Selection.from_profile(graph.profiles[profile_id]).things
    had = sources_from_map(graph, profile_id)
    sources = [
        {
            "id": source["source_id"],
            "label": graph.label(source["source_id"]),
            "kind": graph.kind(source["source_id"]),
            "availability": source["availability"],
            "worked_by_then": source["worked_by_then"],
            "not_known_worked": source["not_known_worked"],
            "examples": source["examples"],
            "listed": source["source_id"] in listed,
            "from_map": source["source_id"] in had and source["source_id"] not in listed,
        }
        for source in place["sources"]
    ]
    sources.sort(key=lambda source: (source["availability"] != "yes", source["label"].lower()))
    return {
        "cliopatria": place["cliopatria"],
        "years": [place["from_year"], place["to_year"]],
        "cliopatria_years": [place["cliopatria_from_year"], place["cliopatria_to_year"]],
        "cliopatria_rows": place["cliopatria_rows"],
        "wikidata": place["wikidata"],
        "release": place["cliopatria_release"],
        "area": place["geojson"],
        "sources": sources,
    }
