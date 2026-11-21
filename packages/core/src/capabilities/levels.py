"""Tech levels: how many steps something is from primitive materials (ADR 0018).

Natural materials are level 0. A route sits at the highest level among its requirements, and a thing is one step above
its easiest route. Levels only ORDER items for display (top N first); they never decide whether something is shown.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .graph import Graph
from .reasoner import Action, Backward, Necessity, condition_rhs, known_quantities
from .tristate import Tri, compare

UNREACHABLE = math.inf


@dataclass(frozen=True)
class Levels:
    """Tech levels and certain-prerequisite counts, keyed by thing id or 'verb:target'.

    `routes` holds the level of each thing and effect route (the highest level among its requirements). Verb routes
    are left out because their level depends on the target.
    """

    levels: dict[str, int | None]
    prerequisites: dict[str, int]
    routes: dict[str, int | None]

    def of(self, key: str) -> int | None:
        return self.levels.get(key)

    def rank(self, key: str, label: str, level: int | None = None) -> tuple:
        """Sort key: highest level first, then most prerequisites, then label. Items without a level go last.

        Pass `level` to override the node's own level (an effect at a specific threshold).
        """
        level = self.levels.get(key) if level is None else level
        return (level is None, -(level or 0), -self.prerequisites.get(key, 0), label.lower())


def compute_levels(graph: Graph) -> Levels:
    solver = _LevelSolver(graph)
    levels = {key: _finite(value) for key, value in solver.solve().items()}
    routes = {rid: _finite(solver.route_level(rid)) for rid, route in graph.routes.items() if "verb" not in route["achieves"]}
    return Levels(levels, _prerequisite_counts(graph, solver.actions), routes)


def _finite(value: float) -> int | None:
    return None if value == UNREACHABLE else int(value)


def action_key(action: Action) -> str:
    return f"{action[0]}:{action[1]}"


class _LevelSolver:
    def __init__(self, graph: Graph) -> None:
        self.g = graph
        self.quantities = known_quantities(graph)
        self.things: dict[str, float] = {
            thing_id: 0 if graph.is_natural(thing_id) else UNREACHABLE
            for thing_id, thing in graph.things.items() if thing["kind"] != "technique"
        }
        self.actions: dict[Action, float] = {(verb, target): UNREACHABLE for verb in graph.verbs for target in graph.targets_for(verb)}
        for route in graph.routes.values():
            for requirement in route["requires"]:
                if requirement["role"] == "action":
                    self.actions.setdefault((requirement["verb"], requirement["target"]), UNREACHABLE)

    def solve(self) -> dict[str, float]:
        # Levels start at infinity and only ever decrease, so repeating until nothing changes terminates, even
        # through cycles (charcoal needs a fire; a fire can burn charcoal).
        changed = True
        while changed:
            changed = False
            for thing_id in self.things:
                changed |= self._lower(self.things, thing_id, self._thing_level(thing_id))
            for action in self.actions:
                changed |= self._lower(self.actions, action, self._action_level(action))
        return {**self.things, **{action_key(action): level for action, level in self.actions.items()}}

    @staticmethod
    def _lower(table: dict, key, candidate: float) -> bool:
        if candidate < table[key]:
            table[key] = candidate
            return True
        return False

    def _thing_level(self, thing_id: str) -> float:
        thing = self.g.things[thing_id]
        if thing["kind"] == "category":
            return min((self.things.get(member, UNREACHABLE) for member in self.g.members(thing_id)), default=UNREACHABLE)
        routes = self.g.routes_producing.get(thing_id, []) + (self.g.routes_achieving.get(thing_id, []) if thing["kind"] == "effect" else [])
        return 1 + min((self._route_level(route_id, None) for route_id in routes), default=UNREACHABLE)

    def _action_level(self, action: Action) -> float:
        verb, target = action
        return 1 + min((self._route_level(route_id, target) for route_id in self.g.verb_routes(verb, target)), default=UNREACHABLE)

    def route_level(self, route_id: str, target: str | None = None) -> float:
        return self._route_level(route_id, target)

    def _route_level(self, route_id: str, target: str | None) -> float:
        return max((self._requirement_level(r, target) for r in self.g.routes[route_id]["requires"]), default=0)

    def _requirement_level(self, requirement: dict, target: str | None) -> float:
        role = requirement["role"]
        if role == "action":
            return self.actions.get((requirement["verb"], requirement["target"]), UNREACHABLE)
        if role == "effect":
            return self._effect_level(requirement, target)
        candidates = [requirement["thing"]] if "thing" in requirement else sorted(self.g.members(requirement["category"]))
        return min((self.things.get(c, UNREACHABLE) for c in candidates if self._could_meet(c, requirement, target)), default=UNREACHABLE)

    def _effect_level(self, requirement: dict, target: str | None) -> float:
        """The easiest effect route whose output could meet the requirement's threshold."""
        levels = []
        for route_id in self.g.routes_achieving.get(requirement["effect"], []):
            provides = self.g.routes[route_id].get("provides", {})
            fits = [compare(provides.get(c["quantity"]), c["op"], condition_rhs(self.g, self.quantities, c, target))
                    for c in requirement.get("where", [])]
            if Tri.NO not in fits:
                levels.append(1 + self._route_level(route_id, None))
        return min(levels, default=UNREACHABLE)

    def _could_meet(self, candidate: str, requirement: dict, target: str | None) -> bool:
        return all(
            compare(self.quantities.get(candidate, {}).get(c["quantity"]), c["op"], condition_rhs(self.g, self.quantities, c, target)) != Tri.NO
            for c in requirement.get("where", [])
        )


def _prerequisite_counts(graph: Graph, actions: dict[Action, float]) -> dict[str, int]:
    """How many things, categories, actions and effects each item certainly needs (the ADR 0018 tie-breaker)."""
    backward = Backward(graph)
    counts = {
        thing_id: _count(backward.of_thing(thing_id))
        for thing_id, thing in graph.things.items() if thing["kind"] in ("material", "artifact")
    }
    counts.update({action_key(action): _count(backward.of_action(*action)) for action in actions})
    return counts


def _count(need: Necessity) -> int:
    return len(need.things) + len(need.categories) + len(need.actions) + len(need.effects)
