import shutil
from pathlib import Path

import pytest

from capabilities.graph import Graph

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def graph() -> Graph:
    return Graph.load(REPO_ROOT)


@pytest.fixture
def data_copy(tmp_path: Path) -> Path:
    """A throwaway copy of the schemas and data, for tests that break files on purpose."""
    for directory in ("schema", "data", "examples"):
        shutil.copytree(REPO_ROOT / directory, tmp_path / directory)
    return tmp_path


def _route(route_id: str, achieves: dict, requires: list[dict], **extra) -> dict:
    route = {"id": route_id, "kind": "route", "label": route_id.replace("-", " ").capitalize(), "achieves": achieves,
             "requires": requires, "references": []}
    if "thing" in achieves:
        route["outputs"] = [{"thing": achieves["thing"]}]
    return {**route, **extra}


@pytest.fixture
def workshop(tmp_path: Path) -> Graph:
    """A small synthetic graph with a cycle, a heat threshold, a category, and a target-relative condition.

    Levels by construction: wood, flint, granite 0; knife 1; ember 2 (via wood + knife, not via charcoal);
    charcoal 3; pot 2 (the open fire is hot enough); metal 5 (only the furnace is); relic has no route.
    Flint is regional, so with nothing selected only the open fire is reachable.
    """
    def material(thing_id, natural=True, **extra):
        thing = {"id": thing_id, "kind": "material", "label": thing_id.capitalize(), "origin": "natural" if natural else "produced"}
        if natural:
            thing["availability"] = "ubiquitous"
        return {**thing, **extra}

    heat_at_least = lambda temperature: {"role": "effect", "effect": "heat",  # noqa: E731
                                         "where": [{"quantity": "temperature_c", "op": ">=", "value": temperature}]}
    things = {
        "wood": material("wood", quantities={"hardness_mohs": 2}),
        "flint": material("flint", availability="regional"),
        "granite": material("granite", availability="regional", quantities={"hardness_mohs": [6, 7]}),
        "knife": {"id": "knife", "kind": "artifact", "label": "Knife", "is_a": ["blade"], "quantities": {"hardness_mohs": 5}},
        "ember": material("ember", natural=False),
        "charcoal": material("charcoal", natural=False),
        "pot": {"id": "pot", "kind": "artifact", "label": "Pot"},
        "metal": material("metal", natural=False),
        "relic": {"id": "relic", "kind": "artifact", "label": "Relic"},
        "blade": {"id": "blade", "kind": "category", "label": "Blade"},
        "heat": {"id": "heat", "kind": "effect", "label": "Heat", "dimensions": ["temperature_c"]},
        "knapping": {"id": "knapping", "kind": "technique", "label": "Knapping"},
    }
    routes = [
        _route("knap-knife", {"thing": "knife"}, [{"role": "consumed", "thing": "flint"}], techniques=["knapping"]),
        _route("ember-from-charcoal", {"thing": "ember"}, [{"role": "consumed", "thing": "charcoal"}]),
        _route("ember-by-friction", {"thing": "ember"}, [{"role": "consumed", "thing": "wood"}, {"role": "tool", "category": "blade"}]),
        _route("char-wood", {"thing": "charcoal"}, [{"role": "consumed", "thing": "wood"}, {"role": "consumed", "thing": "ember"}]),
        _route("open-fire", {"effect": "heat"}, [{"role": "consumed", "thing": "wood"}], provides={"temperature_c": [600, 800]}),
        _route("furnace", {"effect": "heat"}, [{"role": "consumed", "thing": "charcoal"}], provides={"temperature_c": 1200}),
        _route("fire-pot", {"thing": "pot"}, [heat_at_least(500)]),
        _route("smelt-metal", {"thing": "metal"}, [heat_at_least(1000), {"role": "consumed", "thing": "ember"}]),
        _route("cut-with-blade", {"verb": "cut"}, [{"role": "tool", "category": "blade",
                                                   "where": [{"quantity": "hardness_mohs", "op": ">=", "value": "target.hardness_mohs"}]}]),
    ]
    return Graph(
        tmp_path,
        quantities={
            "temperature_c": {"id": "temperature_c", "kind": "quantity", "label": "Temperature", "unit": "°C"},
            "hardness_mohs": {"id": "hardness_mohs", "kind": "quantity", "label": "Hardness (Mohs)", "unit": "Mohs"},
        },
        things=things,
        verbs={"cut": {"id": "cut", "kind": "verb", "label": "Cut", "params": {"target": {"kinds": ["material"]}}}},
        routes={route["id"]: route for route in routes},
    )
