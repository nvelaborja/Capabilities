"""Reasoning over the graph: the three questions.

- Q1 `need_tree` / `Backward`: what would it take to make or do X?
- Q2 `explore`: given what a group made or did (selected), what else was within reach?
- Q3 `assess_job`: could a concrete job be done, how long would it take, and how precise could it be?

Semantics (see docs/data-format.md, "Reasoning rules"):
- A thing is reachable if ANY of its routes is satisfied; a route is satisfied if ALL its requirements are.
- Know-how never gates a route. Routes list techniques for description only.
- Ubiquitous natural materials are free; everything else must be selected, implied, or produced.
- Comparisons over ranges are three-valued (yes / maybe / no); missing data is "maybe".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .graph import Graph, achieved_id
from .tristate import Tri, as_range, compare

Action = tuple[str, str]  # (verb, target)
Bound = tuple[str, float]  # (operator, value), e.g. (">=", 1100)

LOWER_BOUND_OPS = (">=", ">")
UPPER_BOUND_OPS = ("<=", "<")


# ====================================================================== selections


@dataclass(frozen=True)
class Selection:
    """Things a group had and actions it performed."""

    things: frozenset[str] = frozenset()
    actions: frozenset[Action] = frozenset()

    @classmethod
    def parse(cls, items: Iterable[str]) -> "Selection":
        """Parse ids like 'copper' and actions like 'cut:granite'."""
        things, actions = set(), set()
        for item in items:
            if ":" in item:
                verb, target = item.split(":", 1)
                actions.add((verb, target))
            else:
                things.add(item)
        return cls(frozenset(things), frozenset(actions))

    @classmethod
    def from_profile(cls, profile: dict) -> "Selection":
        things = {item["id"] for item in profile["includes"] if "id" in item}
        actions = {(item["verb"], item["target"]) for item in profile["includes"] if "verb" in item}
        return cls(frozenset(things), frozenset(actions))

    def __or__(self, other: "Selection") -> "Selection":
        return Selection(self.things | other.things, self.actions | other.actions)

    def __sub__(self, other: "Selection") -> "Selection":
        return Selection(self.things - other.things, self.actions - other.actions)

    def items(self) -> list[str]:
        return sorted(self.things) + sorted(f"{verb}:{target}" for verb, target in self.actions)

    def unknown_ids(self, graph: Graph) -> list[str]:
        unknown = [thing for thing in self.things if graph.kind(thing) not in ("material", "artifact")]
        for verb, target in self.actions:
            if verb not in graph.verbs:
                unknown.append(f"{verb}:{target} (unknown verb)")
            elif target not in graph.things:
                unknown.append(f"{verb}:{target} (unknown target)")
        return sorted(unknown)


# ====================================================================== backward inference (Q1)


@dataclass
class Necessity:
    """What something certainly required: everything needed by EVERY route to it, recursively."""

    things: set[str] = field(default_factory=set)
    categories: set[str] = field(default_factory=set)
    actions: set[Action] = field(default_factory=set)
    techniques: set[str] = field(default_factory=set)
    # effect id -> quantity -> bound, e.g. {"heat": {"temperature_c": (">=", 1100)}}
    effects: dict[str, dict[str, Bound]] = field(default_factory=dict)

    def add_all(self, other: "Necessity") -> None:
        """Combine needs that all hold at once (within one route, or across several selected items)."""
        self.things |= other.things
        self.categories |= other.categories
        self.actions |= other.actions
        self.techniques |= other.techniques
        for effect, bounds in other.effects.items():
            mine = self.effects.setdefault(effect, {})
            for quantity, bound in bounds.items():
                mine[quantity] = _stronger(mine.get(quantity), bound)

    @staticmethod
    def common(alternatives: list["Necessity"]) -> "Necessity":
        """What every alternative route needs.

        For effects this keeps the WEAKEST bound shared by every route (e.g. one route needs >= 900 °C and another
        >= 1200 °C, so the certain need is >= 900 °C). A quantity is kept only if every route constrains it in the
        same direction. This is sound (each route's own bound implies the merged one) but lossy: see
        docs/data-format.md, "Merging effect thresholds", for the side effects.
        """
        if not alternatives:
            return Necessity()
        first, *rest = alternatives
        result = Necessity(
            things=set.intersection(first.things, *(n.things for n in rest)),
            categories=set.intersection(first.categories, *(n.categories for n in rest)),
            actions=set.intersection(first.actions, *(n.actions for n in rest)),
            techniques=set.intersection(first.techniques, *(n.techniques for n in rest)),
        )
        shared_effects = set(first.effects).intersection(*(n.effects for n in rest))
        for effect in shared_effects:
            merged: dict[str, Bound] = {}
            shared_quantities = set(first.effects[effect]).intersection(*(n.effects[effect] for n in rest))
            for quantity in shared_quantities:
                bounds = [n.effects[effect][quantity] for n in alternatives]
                weakest = _weakest(bounds)
                if weakest is not None:
                    merged[quantity] = weakest
            if merged:
                result.effects[effect] = merged
        return result

    def to_dict(self, graph: Graph) -> dict:
        return {
            "things": sorted(self.things),
            "categories": sorted(self.categories),
            "actions": sorted(f"{verb}:{target}" for verb, target in self.actions),
            "techniques": sorted(self.techniques),
            "effects": {
                effect: {quantity: f"{op} {_fmt(value)}" for quantity, (op, value) in sorted(bounds.items())}
                for effect, bounds in sorted(self.effects.items())
            },
        }


def _stronger(current: Bound | None, new: Bound) -> Bound:
    if current is None or current[0] != new[0]:
        # Mixed directions on one quantity are rare; keep the newest rather than inventing a combined bound.
        return new
    if new[0] in LOWER_BOUND_OPS:
        return new if new[1] > current[1] else current
    return new if new[1] < current[1] else current


def _weakest(bounds: list[Bound]) -> Bound | None:
    ops = {op for op, _ in bounds}
    if ops <= set(LOWER_BOUND_OPS):
        return (">=", min(value for _, value in bounds))
    if ops <= set(UPPER_BOUND_OPS):
        return ("<=", max(value for _, value in bounds))
    return None


def _fmt(value: float) -> str:
    return f"{value:g}"


class Backward:
    """Backward inference: from something a group had or did, to what it certainly needed."""

    def __init__(self, graph: Graph) -> None:
        self.g = graph

    def of_selection(self, selection: Selection) -> Necessity:
        result = Necessity()
        for thing in selection.things:
            result.add_all(self.of_thing(thing))
        for verb, target in selection.actions:
            result.add_all(self.of_action(verb, target))
        return result

    def of_thing(self, thing: str, stack: frozenset = frozenset()) -> Necessity:
        return self._of_routes(("thing", thing), self.g.routes_achieving.get(thing, []), None, stack)

    def of_action(self, verb: str, target: str, stack: frozenset = frozenset()) -> Necessity:
        return self._of_routes(("action", verb, target), self.g.verb_routes(verb, target), target, stack)

    def _of_routes(self, key: tuple, route_ids: list[str], target: str | None, stack: frozenset) -> Necessity:
        if not route_ids or key in stack:
            return Necessity()
        stack = stack | {key}
        return Necessity.common([self._of_route(route_id, target, stack) for route_id in route_ids])

    def _of_route(self, route_id: str, target: str | None, stack: frozenset) -> Necessity:
        route = self.g.routes[route_id]
        need = Necessity(techniques=set(route.get("techniques", [])))
        for requirement in route["requires"]:
            role = requirement["role"]
            if role == "effect":
                bounds = {}
                for condition in requirement.get("where", []):
                    value = _condition_number(self.g, condition, target)
                    if value is not None:
                        bounds[condition["quantity"]] = (condition["op"], value)
                need.add_all(Necessity(effects={requirement["effect"]: bounds} if bounds else {}))
            elif role == "action":
                action = (requirement["verb"], requirement["target"])
                need.actions.add(action)
                need.add_all(self.of_action(*action, stack))
            elif "thing" in requirement:
                need.things.add(requirement["thing"])
                need.add_all(self.of_thing(requirement["thing"], stack))
            else:
                need.categories.add(requirement["category"])
        return need


def _condition_number(graph: Graph, condition: dict, target: str | None) -> float | None:
    """The right-hand side of a condition as a single number (the generous end for backward inference)."""
    if "band" in condition:
        return graph.band(condition["quantity"], condition["band"]).get("min", 0.0)
    value = condition["value"]
    if isinstance(value, str):
        if target is None:
            return None
        target_value = graph.things[target].get("quantities", {}).get(value.split(".", 1)[1])
        if target_value is None:
            return None
        low, high = as_range(target_value)
        return low if condition["op"] in LOWER_BOUND_OPS else high
    return float(value)


def need_tree(graph: Graph, node: str, max_depth: int = 12) -> dict:
    """Q1: the AND/OR tree of everything it would take to make a thing or perform an action ('cut:granite')."""
    if ":" in node:
        verb, target = node.split(":", 1)
        return _action_node(graph, verb, target, 0, frozenset(), max_depth)
    return _thing_node(graph, node, 0, frozenset(), max_depth)


def _thing_node(graph: Graph, thing_id: str, depth: int, path: frozenset, max_depth: int) -> dict:
    thing = graph.things[thing_id]
    node = {"type": "thing", "id": thing_id, "label": thing.get("label", thing_id), "kind": thing["kind"]}
    if thing["kind"] == "material" and thing.get("origin") == "natural":
        node["natural"] = thing.get("availability")
    route_ids = graph.routes_achieving.get(thing_id, [])
    if thing_id in path:
        node["repeat"] = True
    elif depth >= max_depth and route_ids:
        node["truncated"] = True
    else:
        node["routes"] = [_route_node(graph, rid, None, depth, path | {thing_id}, max_depth) for rid in route_ids]
    return node


def _action_node(graph: Graph, verb: str, target: str, depth: int, path: frozenset, max_depth: int) -> dict:
    key = f"{verb}:{target}"
    node = {"type": "action", "id": key, "label": f"{graph.label(verb)} {graph.label(target).lower()}"}
    if key in path:
        node["repeat"] = True
    elif depth >= max_depth:
        node["truncated"] = True
    else:
        node["routes"] = [_route_node(graph, rid, target, depth, path | {key}, max_depth) for rid in graph.verb_routes(verb, target)]
    return node


def _route_node(graph: Graph, route_id: str, target: str | None, depth: int, path: frozenset, max_depth: int) -> dict:
    route = graph.routes[route_id]
    requirements = []
    for requirement in route["requires"]:
        if requirement["role"] == "action":
            child = _action_node(graph, requirement["verb"], requirement["target"], depth + 1, path, max_depth)
        elif "thing" in requirement:
            child = _thing_node(graph, requirement["thing"], depth + 1, path, max_depth)
        elif "effect" in requirement:
            child = _effect_node(graph, requirement, target, depth + 1, path, max_depth)
        else:
            child = {"type": "category", "id": requirement["category"], "label": graph.label(requirement["category"]),
                     "members": sorted(graph.members(requirement["category"]))}
        child["role"] = requirement["role"]
        if requirement.get("where"):
            child["where"] = [_describe_condition(c) for c in requirement["where"]]
        requirements.append(child)
    return {"type": "route", "id": route_id, "label": route.get("label", route_id),
            "techniques": route.get("techniques", []), "requires": requirements}


def _effect_node(graph: Graph, requirement: dict, target: str | None, depth: int, path: frozenset, max_depth: int) -> dict:
    """An effect requirement, expanded into the effect routes whose output could meet its conditions."""
    effect = requirement["effect"]
    node = {"type": "effect", "id": effect, "label": graph.label(effect)}
    key = f"effect:{effect}"
    if key in path:
        node["repeat"] = True
        return node
    if depth >= max_depth:
        node["truncated"] = True
        return node
    routes, excluded = [], []
    for route_id in graph.routes_achieving.get(effect, []):
        provides = graph.routes[route_id].get("provides", {})
        fits = [compare(provides.get(c["quantity"]), c["op"], _condition_number(graph, c, target)) for c in requirement.get("where", [])]
        if Tri.NO in fits:
            excluded.append(route_id)
        else:
            routes.append(_route_node(graph, route_id, None, depth, path | {key}, max_depth))
    node["routes"] = routes
    if excluded:
        node["too_weak"] = excluded
    return node


def condition_rhs(graph: Graph, quantities: dict[str, dict], condition: dict, target: str | None):
    """The value a condition compares against: a number, a band's lower edge, or the target's quantity (or None)."""
    if "band" in condition:
        return graph.band(condition["quantity"], condition["band"]).get("min", 0.0)
    value = condition["value"]
    if isinstance(value, str):
        if target is None:
            return None
        return quantities.get(target, {}).get(value.split(".", 1)[1])
    return value


def known_quantities(graph: Graph) -> dict[str, dict]:
    """Each thing's quantities, plus any that a route states for its outputs (e.g. hardened steel's hardness)."""
    quantities = {thing_id: dict(thing.get("quantities", {})) for thing_id, thing in graph.things.items()}
    for route in graph.routes.values():
        for output in route.get("outputs", []):
            for quantity, value in output.get("quantities", {}).items():
                quantities[output["thing"]].setdefault(quantity, value)
    return quantities


def _describe_condition(condition: dict) -> str:
    rhs = condition.get("band") or condition.get("value")
    return f"{condition['quantity']} {condition['op']} {rhs}"


# ====================================================================== forward reachability (Q2)


class Reachability:
    """Forward closure: everything reachable from a starting selection, as yes / maybe / no."""

    def __init__(self, graph: Graph, base: Selection, asserted_effects: dict[str, dict[str, Bound]] | None = None) -> None:
        self.g = graph
        self.base = base
        self.asserted_effects = asserted_effects or {}
        self.status: dict[str, Tri] = {}
        self.quantities: dict[str, dict] = {tid: dict(t.get("quantities", {})) for tid, t in graph.things.items()}
        for thing_id in graph.things:
            self.status[thing_id] = Tri.YES if thing_id in base.things or graph.is_free(thing_id) else Tri.NO
        self._action_cache: dict[tuple, Tri] = {}
        self._in_progress: set[tuple] = set()
        self._solve()

    def _solve(self) -> None:
        # Statuses only ever increase, so this repeat-until-stable loop terminates.
        changed = True
        while changed:
            changed = False
            self._action_cache.clear()
            for route_id in self.g.thing_routes():
                status = self.route_status(route_id, None)
                if status == Tri.NO:
                    continue
                for output in self.g.routes[route_id].get("outputs", []):
                    if status > self.status[output["thing"]]:
                        self.status[output["thing"]] = status
                        changed = True
                    for quantity, value in output.get("quantities", {}).items():
                        self.quantities[output["thing"]].setdefault(quantity, value)
        self._action_cache.clear()

    # ------------------------------------------------------------------ statuses

    def route_status(self, route_id: str, target: str | None) -> Tri:
        statuses = [self.requirement_status(req, target) for req in self.g.routes[route_id]["requires"]]
        return min(statuses, default=Tri.YES)

    def requirement_status(self, requirement: dict, target: str | None) -> Tri:
        role = requirement["role"]
        if role == "effect":
            return self.effect_status(requirement["effect"], requirement.get("where", []), target)
        if role == "action":
            return self.action_status(requirement["verb"], requirement["target"])
        candidates = [requirement["thing"]] if "thing" in requirement else sorted(self.g.members(requirement["category"]))
        best = Tri.NO
        for candidate in candidates:
            if self.status.get(candidate, Tri.NO) == Tri.NO:
                continue
            conditions = [
                compare(self.quantities[candidate].get(c["quantity"]), c["op"], self._rhs(c, target))
                for c in requirement.get("where", [])
            ]
            best = max(best, min([self.status[candidate], *conditions]))
        return best

    def effect_status(self, effect: str, where: list[dict], target: str | None) -> Tri:
        best = Tri.NO
        for route_id in self.g.routes_achieving.get(effect, []):
            route_status = self.route_status(route_id, None)
            if route_status == Tri.NO:
                continue
            provides = self.g.routes[route_id].get("provides", {})
            conditions = [compare(provides.get(c["quantity"]), c["op"], self._rhs(c, target)) for c in where]
            best = max(best, min([route_status, *conditions]))
        asserted = self.asserted_effects.get(effect)
        if asserted is not None:
            best = max(best, self._asserted_status(asserted, where, target))
        return best

    def _asserted_status(self, asserted: dict[str, Bound], where: list[dict], target: str | None) -> Tri:
        """An implied effect level ("they reached at least 1100 °C") satisfies requirements at or below it."""
        result = Tri.YES
        for condition in where:
            bound = asserted.get(condition["quantity"])
            if bound is None or bound[0] not in LOWER_BOUND_OPS or condition["op"] not in LOWER_BOUND_OPS:
                return Tri.NO
            result = min(result, compare(bound[1], condition["op"], self._rhs(condition, target)))
        return result

    def action_status(self, verb: str, target: str) -> Tri:
        key = (verb, target)
        if key in self.base.actions:
            return Tri.YES
        if key in self._action_cache:
            return self._action_cache[key]
        if key in self._in_progress:
            return Tri.NO
        self._in_progress.add(key)
        try:
            status = max((self.route_status(rid, target) for rid in self.g.verb_routes(verb, target)), default=Tri.NO)
        finally:
            self._in_progress.discard(key)
        self._action_cache[key] = status
        return status

    def _rhs(self, condition: dict, target: str | None):
        return condition_rhs(self.g, self.quantities, condition, target)

    def requirement_label(self, requirement: dict) -> str:
        if requirement["role"] == "action":
            return f"action {requirement['verb']}({requirement['target']})"
        key = requirement.get("thing") or requirement.get("category") or requirement.get("effect")
        label = f"{requirement['role']} {key}"
        if "category" in requirement:
            label += " (any)"
        for condition in requirement.get("where", []):
            label += f" [{_describe_condition(condition)}]"
        return label


@dataclass
class ExploreResult:
    selected: Selection
    hypothetical: Selection
    implied: Necessity
    reachable: list[str]
    maybe: list[str]
    actions: dict[str, dict[str, str]]
    near_misses: list[dict]
    warnings: list[str]
    # Kept so callers can ask follow-up questions (statuses, explanations) without recomputing.
    reach: Reachability | None = field(default=None, repr=False, compare=False)

    def to_dict(self, graph: Graph) -> dict:
        return {
            "selected": self.selected.items(),
            "hypothetical": self.hypothetical.items(),
            "implied": self.implied.to_dict(graph),
            "reachable": self.reachable,
            "maybe": self.maybe,
            "actions": self.actions,
            "near_misses": self.near_misses,
            "warnings": self.warnings,
        }


def explore(graph: Graph, selected: Selection, hypothetical: Selection = Selection()) -> ExploreResult:
    """Q2: given what a group made or did, what else was within their reach?"""
    implied, reach = closure(graph, selected, hypothetical)
    base = reach.base

    def produced(thing_id: str) -> bool:
        thing = graph.things[thing_id]
        return thing["kind"] == "artifact" or (thing["kind"] == "material" and thing.get("origin") == "produced")

    reachable = sorted(t for t, s in reach.status.items() if s == Tri.YES and produced(t) and t not in base.things)
    maybe = sorted(t for t, s in reach.status.items() if s == Tri.MAYBE and produced(t) and t not in base.things)

    actions: dict[str, dict[str, str]] = {}
    for verb in sorted(graph.verbs):
        statuses = {target: reach.action_status(verb, target) for target in graph.targets_for(verb)}
        if len(set(statuses.values())) == 1:
            # No route depends on the target (e.g. move), so one answer covers every target.
            status = next(iter(statuses.values()))
            if status != Tri.NO:
                actions[verb] = {"(any)": status.label}
            continue
        target_quantities = _target_quantities(graph, verb)
        found = {}
        for target, status in statuses.items():
            # A "maybe" caused only by the target lacking data (e.g. the hardness of water) is noise, not uncertainty.
            has_data = all(q in reach.quantities.get(target, {}) for q in target_quantities)
            if status == Tri.YES or (status == Tri.MAYBE and has_data):
                found[target] = status.label
        if found:
            actions[verb] = found

    near_misses = []
    for route_id in graph.thing_routes():
        thing = achieved_id(graph.routes[route_id])
        if reach.status[thing] != Tri.NO:
            continue
        missing = [reach.requirement_label(r) for r in graph.routes[route_id]["requires"] if reach.requirement_status(r, None) == Tri.NO]
        if len(missing) == 1:
            near_misses.append({"thing": thing, "route": route_id, "missing": missing[0]})

    warnings = _regional_warnings(graph, selected | hypothetical, implied)
    return ExploreResult(selected, hypothetical, implied, reachable, maybe, actions, near_misses, warnings, reach)


def _target_quantities(graph: Graph, verb: str) -> set[str]:
    """Quantities of the target that any route for this verb compares against (e.g. hardness_mohs for cut)."""
    found = set()
    for route_id in graph.routes_achieving.get(verb, []):
        for requirement in graph.routes[route_id]["requires"]:
            for condition in requirement.get("where", []):
                value = condition.get("value")
                if isinstance(value, str):
                    found.add(value.split(".", 1)[1])
    return found


def _regional_warnings(graph: Graph, chosen: Selection, implied: Necessity) -> list[str]:
    warnings = []
    for thing in sorted(implied.things - chosen.things):
        if graph.is_regional(thing):
            regions = "; ".join(graph.things[thing].get("regions", [])) or "unknown regions"
            warnings.append(f"Implies access to {thing}, which is only found in some places ({regions}). It may have been traded.")
    for category in sorted(implied.categories):
        members = graph.members(category)
        if members and all(graph.is_regional(m) or graph.kind(m) != "material" for m in members) and not (members & chosen.things):
            sources = ", ".join(sorted(m for m in members if graph.is_regional(m)))
            warnings.append(f"Implies access to some {category} ({sources}); all known sources are regional, so it may have been traded.")
    return warnings


# ====================================================================== feasibility (Q3)


@dataclass
class RouteAssessment:
    route: str
    available: Tri
    verdict: str
    hours: tuple[float, float] | None = None
    duration_bands: tuple[str | None, str | None] | None = None
    units: int = 1
    precision: str | None = None
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "route": self.route, "available": self.available.label, "verdict": self.verdict,
            "hours": list(self.hours) if self.hours else None,
            "duration_bands": list(self.duration_bands) if self.duration_bands else None,
            "units": self.units, "precision": self.precision, "reasons": self.reasons,
        }


@dataclass
class StepAssessment:
    label: str
    verb: str
    target: str
    routes: list[RouteAssessment]
    best: RouteAssessment | None

    def to_dict(self) -> dict:
        return {"label": self.label, "verb": self.verb, "target": self.target,
                "best": self.best.route if self.best else None, "routes": [r.to_dict() for r in self.routes]}


@dataclass
class JobAssessment:
    job: str
    verdict: str
    steps: list[StepAssessment]
    total_hours: tuple[float, float] | None
    total_bands: tuple[str | None, str | None] | None
    reasons: list[str]

    def to_dict(self) -> dict:
        return {"job": self.job, "verdict": self.verdict, "steps": [s.to_dict() for s in self.steps],
                "total_hours": list(self.total_hours) if self.total_hours else None,
                "total_bands": list(self.total_bands) if self.total_bands else None, "reasons": self.reasons}


# Ordered from best to worst, for picking each step's best route and the job's overall verdict.
VERDICTS = ["feasible", "uncertain", "insufficient data", "no known route meets these constraints", "not available"]


def assess_job(graph: Graph, job: dict, reach: Reachability) -> JobAssessment:
    """Q3: check a job against every route that could do each of its steps."""
    steps = job.get("steps") or [{"label": job.get("label", job["id"]), "verb": job["verb"], "target": job["target"],
                                  "parameters": job["parameters"]}]
    job_limits = job.get("limits", {})
    step_results = []
    for index, step in enumerate(steps):
        limits = {**_inherited_limits(job_limits, single_step=len(steps) == 1), **step.get("limits", {})}
        if index == len(steps) - 1 and "precision" in job_limits:
            limits["precision"] = job_limits["precision"]
        assessments = [_assess_route(graph, reach, rid, step, limits) for rid in graph.verb_routes(step["verb"], step["target"])]
        best = min(assessments, key=lambda a: (VERDICTS.index(a.verdict), a.hours[0] if a.hours else float("inf")), default=None)
        step_results.append(StepAssessment(step.get("label", f"Step {index + 1}"), step["verb"], step["target"], assessments, best))

    reasons: list[str] = []
    bests = [s.best for s in step_results]
    if any(b is None for b in bests):
        verdict = "no known route meets these constraints"
        reasons.append("A step has no route at all.")
    else:
        verdict = max((b.verdict for b in bests), key=VERDICTS.index)
    total = None
    if bests and all(b is not None and b.hours for b in bests):
        total = (sum(b.hours[0] for b in bests), sum(b.hours[1] for b in bests))
        budget = job_limits.get("max_duration_h")
        if budget is not None and len(steps) > 1:
            time_check = compare(budget, ">=", total)
            if time_check == Tri.NO:
                verdict = "no known route meets these constraints"
                reasons.append(f"Even the fastest estimate ({total[0]:,.0f} h) exceeds the {budget:,.0f} h budget.")
            elif time_check == Tri.MAYBE and verdict == "feasible":
                verdict = "uncertain"
                reasons.append("The time estimate straddles the budget.")
    bands = (graph.band_of("duration_h", total[0]), graph.band_of("duration_h", total[1])) if total else None
    return JobAssessment(job.get("id", "(inline job)"), verdict, step_results, total, bands, reasons)


def _inherited_limits(job_limits: dict, single_step: bool) -> dict:
    # Precision applies to the final step only. A multi-step job's time budget is for the total, checked after
    # summing the steps, so it is only passed down when there is a single step.
    keys = ("max_crew", "max_units", "max_duration_h") if single_step else ("max_crew", "max_units")
    return {key: value for key, value in job_limits.items() if key in keys}


def _assess_route(graph: Graph, reach: Reachability, route_id: str, step: dict, limits: dict) -> RouteAssessment:
    route = graph.routes[route_id]
    envelope = route.get("envelope", {})
    target = step["target"]
    available = reach.route_status(route_id, target)
    assessment = RouteAssessment(route_id, available, verdict="feasible")
    hard_no, unknown, uncertain = [], [], []
    requirement_statuses = [(r, reach.requirement_status(r, target)) for r in route["requires"]]
    if available == Tri.NO:
        assessment.verdict = "not available"
        missing = [reach.requirement_label(r) for r, s in requirement_statuses if s == Tri.NO]
        assessment.reasons.append(f"Not reachable from the selection: {'; '.join(missing)}.")
        return assessment
    if available == Tri.MAYBE:
        unsure = [reach.requirement_label(r) for r, s in requirement_statuses if s == Tri.MAYBE]
        uncertain.append(f"Uncertain or missing values for: {'; '.join(unsure)}.")

    # Time: volume / (rate × number of tools working at once)
    rate_info = envelope.get("rate", {})
    rate = next((e for e in rate_info.get("by_target", []) if e["target"] == target), None)
    crew_per_unit = rate_info.get("crew", 1)
    max_crew = limits.get("max_crew")
    if max_crew is not None and crew_per_unit > max_crew:
        hard_no.append(f"Needs a crew of {crew_per_unit} per tool; only {max_crew} available.")
    units = limits.get("max_units", 1)
    if max_crew is not None:
        units = max(1, min(units, max_crew // crew_per_unit))
    assessment.units = units
    volume = step["parameters"].get("volume_cm3")
    if rate is None or volume is None:
        unknown.append("No measured rate for this route on this target.")
    else:
        rate_low, rate_high = as_range(rate["value"])
        volume_low, volume_high = as_range(volume)
        assessment.hours = (volume_low / (rate_high * units), volume_high / (rate_low * units))
        assessment.duration_bands = (graph.band_of("duration_h", assessment.hours[0]), graph.band_of("duration_h", assessment.hours[1]))
        budget = limits.get("max_duration_h")
        if budget is not None:
            # Generous end: only rule a route out if even its fastest estimate is over budget.
            time_check = compare(budget, ">=", assessment.hours)
            if time_check == Tri.NO:
                hard_no.append(f"Even the fastest estimate ({assessment.hours[0]:,.0f} h) exceeds the {budget:,.0f} h budget.")
            elif time_check == Tri.MAYBE:
                uncertain.append("The time estimate straddles the budget.")
        if rate.get("basis") not in ("measured", "derived"):
            uncertain.append(f"The rate is {rate.get('basis')}, not measured.")

    # Precision: route bands are [finest, roughest] the route can achieve.
    required = limits.get("precision")
    bands = envelope.get("precision", {}).get("bands")
    if bands:
        assessment.precision = bands[0] if len(bands) == 1 or bands[0] == bands[-1] else f"{bands[0]}–{bands[-1]}"
    if required:
        if not bands:
            unknown.append(f"No data on the precision this route can reach (required {required}).")
        else:
            finest, roughest = graph.precision_rank(bands[0]), graph.precision_rank(bands[-1])
            needed = graph.precision_rank(required)
            if max(finest, roughest) < needed:
                hard_no.append(f"Reaches {assessment.precision} at best; {required} is required.")
            elif min(finest, roughest) < needed:
                uncertain.append(f"Reaches {assessment.precision}; {required} is required.")

    assessment.reasons = hard_no + unknown + uncertain
    if hard_no:
        assessment.verdict = "no known route meets these constraints"
    elif unknown:
        assessment.verdict = "insufficient data"
    elif uncertain:
        assessment.verdict = "uncertain"
    return assessment


def closure(graph: Graph, selected: Selection, hypothetical: Selection = Selection()) -> tuple[Necessity, Reachability]:
    """Backward then forward: what the selection implies, and everything reachable from selection + implied."""
    implied = Backward(graph).of_selection(selected | hypothetical)
    base = selected | hypothetical | Selection(frozenset(implied.things), frozenset(implied.actions))
    return implied, Reachability(graph, base, implied.effects)
