"""Display-ready shapes for the web UI: the drawable graph, per-node statuses, and first-degree explanations.

The reasoner answers questions; this module turns its answers into what a viewer needs: labels, statuses, levels,
and short human-readable reasons. See ADRs 0015-0020.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from .graph import Graph
from .levels import Levels, action_key
from .reasoner import Action, Backward, ExploreResult, Necessity, Reachability, Selection, condition_rhs
from .tristate import Tri, as_range, compare

# Kinds drawn on the graph. Techniques never gate anything (ADR 0005), so they appear only in details and lists.
DRAWN_KINDS = ("material", "artifact", "category", "effect")
SELECTABLE_KINDS = ("material", "artifact")
OPERATORS = {">=": "≥", ">": ">", "<=": "≤", "<": "<", "==": "="}


class UnknownNode(KeyError):
    """The id is not something the UI can show or explain."""


# ====================================================================== labels and conditions


def action_label(graph: Graph, action: Action) -> str:
    verb, target = action
    return f"{graph.label(verb)} {graph.label(target).lower()}"


def parse_action(key: str) -> Action:
    verb, target = key.split(":", 1)
    return verb, target


def node_label(graph: Graph, key: str) -> str:
    return action_label(graph, parse_action(key)) if ":" in key else graph.label(key)


def format_value(value, unit: str = "") -> str:
    low, high = as_range(value)
    number = f"{low:g}" if low == high else f"{low:g}–{high:g}"
    return f"{number} {unit}".strip()


def describe_condition(graph: Graph, condition: dict, target: str | None = None) -> str:
    """'Temperature ≥ 1100 °C', or 'Hardness ≥ 6–7 Mohs (granite)' when the condition is relative to the target."""
    return f"{quantity_name(graph, condition['quantity'])} {describe_threshold(graph, condition, target)}"


def quantity_name(graph: Graph, quantity: str) -> str:
    """The quantity's label without its parenthetical: 'Hardness (Mohs)' becomes 'Hardness'."""
    return graph.quantities.get(quantity, {}).get("label", quantity).split(" (")[0]


def quantity_value(graph: Graph, quantity: str, value) -> str:
    return "unknown" if value is None else format_value(value, graph.quantities.get(quantity, {}).get("unit", ""))


def describe_threshold(graph: Graph, condition: dict, target: str | None = None) -> str:
    """The right-hand side of a condition: '≥ 1100 °C', '≥ 1 hours (hours)', '≥ 6–7 Mohs (granite)'."""
    quantity = condition["quantity"]
    op = OPERATORS.get(condition["op"], condition["op"])
    if "band" in condition:
        band = graph.band(quantity, condition["band"])
        return f"{op} {quantity_value(graph, quantity, band.get('min', 0))} ({band.get('label', condition['band']).lower()})"
    value = condition["value"]
    if isinstance(value, str):
        target_value = graph.things.get(target, {}).get("quantities", {}).get(value.split(".", 1)[1]) if target else None
        if target_value is None:
            return f"{op} the target's"
        return f"{op} {quantity_value(graph, quantity, target_value)} ({graph.label(target).lower()})"
    return f"{op} {quantity_value(graph, quantity, value)}"


# ====================================================================== the drawable graph


def referenced_actions(graph: Graph) -> set[Action]:
    """Actions some route requires or some profile includes. Other actions are added to the graph on request."""
    found = {(r["verb"], r["target"]) for route in graph.routes.values() for r in route["requires"] if r["role"] == "action"}
    for profile in graph.profiles.values():
        found |= {(item["verb"], item["target"]) for item in profile["includes"] if "verb" in item}
    return found


def graph_view(graph: Graph, levels: Levels, extra_actions: Iterable[Action] = ()) -> dict:
    """Every drawable node and edge. Routes are junction nodes: several into a thing = any of; edges into one = all of."""
    actions = sorted(referenced_actions(graph) | set(extra_actions))
    nodes = [_thing_view(graph, levels, thing_id) for thing_id, thing in sorted(graph.things.items()) if thing["kind"] in DRAWN_KINDS]
    nodes += [_action_view(graph, levels, action) for action in actions]
    edges = []
    for route_id, route in sorted(graph.routes.items()):
        nodes.append(_route_view(graph, levels, route_id))
        edges += _requirement_edges(graph, route_id)
        edges += _product_edges(graph, route_id, actions)
    edges += _membership_edges(graph)
    return {
        "nodes": nodes,
        "edges": edges,
        "verbs": [{"id": verb_id, "label": verb["label"]} for verb_id, verb in sorted(graph.verbs.items())],
        "techniques": [{"id": tid, "label": t["label"]} for tid, t in sorted(graph.things.items()) if t["kind"] == "technique"],
        "actions": [{"id": action_key(a), "label": action_label(graph, a)} for a in all_actions(graph)],
    }


def all_actions(graph: Graph) -> list[Action]:
    """Every verb and target pair the data allows, drawn or not, so search can find and add any of them."""
    return [(verb, target) for verb in sorted(graph.verbs) for target in graph.targets_for(verb)]


def _thing_view(graph: Graph, levels: Levels, thing_id: str) -> dict:
    thing = graph.things[thing_id]
    view = {
        "id": thing_id, "label": thing.get("label", thing_id), "kind": thing["kind"],
        "selectable": thing["kind"] in SELECTABLE_KINDS,
        "level": levels.of(thing_id), "prerequisites": levels.prerequisites.get(thing_id, 0),
    }
    for key in ("origin", "availability", "era"):
        if key in thing:
            view[key] = thing[key]
    return view


def _action_view(graph: Graph, levels: Levels, action: Action) -> dict:
    key = action_key(action)
    return {
        "id": key, "label": action_label(graph, action), "kind": "action", "verb": action[0], "target": action[1],
        "selectable": True, "level": levels.of(key), "prerequisites": levels.prerequisites.get(key, 0),
    }


def _route_view(graph: Graph, levels: Levels, route_id: str) -> dict:
    route = graph.routes[route_id]
    ((achieves_kind, achieves_id),) = route["achieves"].items()
    # Verb routes have no single level (it depends on the target), so theirs is None.
    return {"id": route_id, "label": route.get("label", route_id), "kind": "route", "level": levels.routes.get(route_id),
            "achieves": {"kind": achieves_kind, "id": achieves_id}, "techniques": route.get("techniques", [])}


def requirement_node(requirement: dict) -> str:
    if requirement["role"] == "action":
        return action_key((requirement["verb"], requirement["target"]))
    return requirement.get("thing") or requirement.get("category") or requirement["effect"]


def _requirement_edges(graph: Graph, route_id: str) -> list[dict]:
    edges = []
    for index, requirement in enumerate(graph.routes[route_id]["requires"]):
        edge = {"id": f"{route_id}/requires/{index}", "source": requirement_node(requirement), "target": route_id,
                "kind": "requires", "role": requirement["role"]}
        conditions = [describe_condition(graph, c) for c in requirement.get("where", [])]
        if conditions:
            edge["label"] = " · ".join(conditions)
        edges.append(edge)
    return edges


def _product_edges(graph: Graph, route_id: str, actions: list[Action]) -> list[dict]:
    route = graph.routes[route_id]
    if "thing" in route["achieves"]:
        return [{"id": f"{route_id}/produces/{o['thing']}", "source": route_id, "target": o["thing"], "kind": "produces",
                 "byproduct": bool(o.get("byproduct"))} for o in route.get("outputs", [])]
    if "effect" in route["achieves"]:
        effect = route["achieves"]["effect"]
        return [{"id": f"{route_id}/produces/{effect}", "source": route_id, "target": effect, "kind": "produces", "byproduct": False}]
    # Verb routes connect only to the action nodes present; the others are added on request.
    verb = route["achieves"]["verb"]
    return [{"id": f"{route_id}/performs/{action_key(a)}", "source": route_id, "target": action_key(a), "kind": "performs"}
            for a in actions if a[0] == verb and graph.applies_to(route_id, a[1])]


def _membership_edges(graph: Graph) -> list[dict]:
    return [
        {"id": f"{thing_id}/is_a/{category}", "source": thing_id, "target": category, "kind": "is_a"}
        for thing_id, thing in sorted(graph.things.items()) if thing["kind"] in DRAWN_KINDS
        for category in thing.get("is_a", []) if category in graph.things
    ]


# ====================================================================== statuses


@dataclass
class StatusContext:
    """Everything needed to say where a node stands relative to a selection."""

    graph: Graph
    selected: Selection
    hypothetical: Selection
    implied: Necessity
    reach: Reachability
    near: set[str]

    @classmethod
    def from_explore(cls, graph: Graph, result: ExploreResult) -> "StatusContext":
        return cls(graph, result.selected, result.hypothetical, result.implied, result.reach,
                   {miss["thing"] for miss in result.near_misses})

    def status(self, key: str) -> str:
        """selected | hypothetical | implied | reachable | maybe | near | out."""
        if ":" in key:
            return self._action_status(parse_action(key))
        kind = self.graph.kind(key)
        if kind == "category":
            return self._category_status(key)
        if kind == "effect":
            return self._effect_status(key)
        if key in self.hypothetical.things:
            return "hypothetical"
        if key in self.selected.things:
            return "selected"
        if key in self.implied.things:
            return "implied"
        return _tri_status(self.reach.status.get(key, Tri.NO), near=key in self.near)

    def _action_status(self, action: Action) -> str:
        if action in self.hypothetical.actions:
            return "hypothetical"
        if action in self.selected.actions:
            return "selected"
        if action in self.implied.actions:
            return "implied"
        return _tri_status(self.reach.action_status(*action))

    def _category_status(self, category: str) -> str:
        if category in self.implied.categories:
            return "implied"
        best = max((self.reach.status.get(m, Tri.NO) for m in self.graph.members(category)), default=Tri.NO)
        return _tri_status(best)

    def _effect_status(self, effect: str) -> str:
        if effect in self.implied.effects:
            return "implied"
        return _tri_status(self.reach.effect_status(effect, [], None))

    def route_status(self, route_id: str, actions: Iterable[Action]) -> Tri:
        """A thing or effect route's status. A verb route takes its best status over the given actions."""
        route = self.graph.routes[route_id]
        if "verb" not in route["achieves"]:
            return self.reach.route_status(route_id, None)
        verb = route["achieves"]["verb"]
        targets = [t for v, t in actions if v == verb and self.graph.applies_to(route_id, t)]
        return max((self.reach.route_status(route_id, t) for t in targets), default=Tri.NO)


def _tri_status(tri: Tri, near: bool = False) -> str:
    if tri == Tri.YES:
        return "reachable"
    if tri == Tri.MAYBE:
        return "maybe"
    return "near" if near else "out"


def explore_view(graph: Graph, result: ExploreResult) -> dict:
    """The explore result plus a status for every drawable node and route, and what implies each implied item."""
    context = StatusContext.from_explore(graph, result)
    chosen = result.selected | result.hypothetical
    actions = referenced_actions(graph) | set(chosen.actions) | set(result.implied.actions)
    keys = [tid for tid, t in graph.things.items() if t["kind"] in DRAWN_KINDS] + [action_key(a) for a in actions]
    return {
        **result.to_dict(graph),
        "status": {key: context.status(key) for key in sorted(keys)},
        "route_status": {rid: context.route_status(rid, actions).label for rid in sorted(graph.routes)},
        "implied_by": implied_by(graph, chosen),
        "implied_effects": implied_effects(graph, result.implied),
        "near": near_view(graph, result),
    }


def implied_effects(graph: Graph, implied: Necessity) -> list[dict]:
    """Effect levels the selection certainly reached, readable: Heat, ["Temperature ≥ 1085 °C"]."""
    views = []
    for effect, bounds in sorted(implied.effects.items()):
        conditions = [describe_condition(graph, {"quantity": q, "op": op, "value": value}) for q, (op, value) in sorted(bounds.items())]
        views.append({"id": effect, "label": graph.label(effect), "conditions": conditions})
    return views


def near_view(graph: Graph, result: ExploreResult) -> list[dict]:
    """Things one requirement away, grouped by thing, each route naming what it is missing."""
    reach = result.reach
    grouped: dict[str, list[dict]] = defaultdict(list)
    for miss in result.near_misses:
        route = graph.routes[miss["route"]]
        missing = next(r for r in route["requires"] if reach.requirement_status(r, None) == Tri.NO)
        key = requirement_node(missing)
        grouped[miss["thing"]].append({
            "id": miss["route"], "label": route.get("label", miss["route"]),
            "missing": {"id": key, "label": node_label(graph, key) + (" (any)" if "category" in missing else ""),
                        "kind": "action" if ":" in key else graph.kind(key)},
        })
    return [{"id": thing, "label": graph.label(thing), "routes": routes} for thing, routes in sorted(grouped.items())]


def implied_by(graph: Graph, chosen: Selection) -> dict[str, list[str]]:
    """For each implied item (thing, category, action, effect or technique), the chosen items that imply it."""
    backward = Backward(graph)
    found: dict[str, set[str]] = defaultdict(set)
    for item in chosen.items():
        need = backward.of_action(*parse_action(item)) if ":" in item else backward.of_thing(item)
        keys = [*need.things, *need.categories, *need.techniques, *need.effects, *(action_key(a) for a in need.actions)]
        for key in keys:
            found[key].add(item)
    return {key: sorted(items) for key, items in sorted(found.items())}


# ====================================================================== explain (first-degree dependencies)


def explain(graph: Graph, levels: Levels, context: StatusContext, key: str, everything: bool = False) -> dict:
    """What a node needs, one level deep, marked met / missing / unknown with reasons (ADR 0020).

    With `everything`, also every certain need at every depth, split into missing, uncertain and have.
    """
    kind = _explainable_kind(graph, key)
    view = {"id": key, "label": node_label(graph, key), "kind": kind, "status": context.status(key), "level": levels.of(key),
            "about": about(graph, key), "leads_to": leads_to(graph, levels, context, key)}
    if kind == "category":
        view["members"] = _ranked(levels, [_member_row(graph, levels, context, m) for m in graph.members(key)])
        return view
    target = parse_action(key)[1] if kind == "action" else None
    explainer = _Explainer(graph, levels, context.reach, target)
    view["routes"] = sorted((explainer.route_row(rid) for rid in _routes_for(graph, key, kind)),
                            key=lambda r: (r["missing"], r["uncertain"], r["label"].lower()))
    if everything and kind in ("material", "artifact", "action"):
        view["all"] = _all_dependencies(graph, levels, context, key, kind)
    return view


def _explainable_kind(graph: Graph, key: str) -> str:
    if ":" in key:
        verb, target = parse_action(key)
        if verb not in graph.verbs or target not in graph.things:
            raise UnknownNode(key)
        return "action"
    kind = graph.kind(key)
    if kind not in DRAWN_KINDS:
        raise UnknownNode(key)
    return kind


def about(graph: Graph, key: str) -> dict:
    """What the node is: description, numbers, where it is found, what kinds it belongs to, and its sources."""
    if ":" in key:
        verb, target = parse_action(key)
        return {"description": graph.verbs[verb].get("description"), "target": {"id": target, "label": graph.label(target)},
                "references": []}
    thing = graph.things[key]
    view = {
        "description": thing.get("description"),
        "quantities": [{"id": q, "label": quantity_name(graph, q), "value": quantity_value(graph, q, v)}
                       for q, v in thing.get("quantities", {}).items()],
        "member_of": [{"id": c, "label": graph.label(c)} for c in thing.get("is_a", []) if c in graph.things],
        "references": references(thing),
    }
    for field in ("notes", "origin", "availability", "regions", "era"):
        if thing.get(field):
            view[field] = thing[field].strip() if isinstance(thing[field], str) else thing[field]
    return view


def references(item: dict) -> list[dict]:
    fields = ("citation", "doi", "url", "supports", "status")
    return [{field: ref[field] for field in fields if field in ref} for ref in item.get("references", [])]


def leads_to(graph: Graph, levels: Levels, context: StatusContext, key: str) -> list[dict]:
    """What the node is used to make directly, most advanced first, with the routes that use it."""
    actions = sorted(referenced_actions(graph))
    via: dict[str, list[str]] = defaultdict(list)
    for route_id, route in sorted(graph.routes.items()):
        if any(requirement_node(r) == key for r in route["requires"]):
            for product in _main_products(graph, route_id, actions):
                via[product].append(route.get("label", route_id))
    rows = [{"id": p, "label": node_label(graph, p), "kind": "action" if ":" in p else graph.kind(p), "status": context.status(p),
             "level": levels.of(p), "via": routes} for p, routes in via.items() if p != key]
    return _ranked(levels, rows)


def _main_products(graph: Graph, route_id: str, actions: list[Action]) -> list[str]:
    return [edge["target"] for edge in _product_edges(graph, route_id, actions) if not edge.get("byproduct")]


def _routes_for(graph: Graph, key: str, kind: str) -> list[str]:
    if kind == "action":
        return graph.verb_routes(*parse_action(key))
    if kind == "effect":
        return graph.routes_achieving.get(key, [])
    return graph.routes_producing.get(key, [])


class _Explainer:
    """Builds requirement rows for routes, all relative to one target (for verb routes) or none."""

    def __init__(self, graph: Graph, levels: Levels, reach: Reachability, target: str | None) -> None:
        self.g, self.levels, self.reach, self.target = graph, levels, reach, target

    def route_row(self, route_id: str) -> dict:
        route = self.g.routes[route_id]
        rows = sorted((self.requirement_row(r) for r in route["requires"]),
                      key=lambda row: (_STATUS_RANK[row["status"]], *self.levels.rank(row["id"], row["label"], row["level"])))
        row = {
            "id": route_id, "label": route.get("label", route_id),
            "techniques": [{"id": t, "label": self.g.label(t)} for t in route.get("techniques", [])],
            "status": self.reach.route_status(route_id, self.target).label,
            "missing": sum(row["status"] == "no" for row in rows),
            "uncertain": sum(row["status"] == "maybe" for row in rows),
            "requirements": rows,
            "references": references(route),
        }
        byproducts = [{"id": o["thing"], "label": self.g.label(o["thing"])} for o in route.get("outputs", []) if o.get("byproduct")]
        if byproducts:
            row["byproducts"] = byproducts
        provides = [f"{quantity_name(self.g, q)} up to {quantity_value(self.g, q, v)}" for q, v in route.get("provides", {}).items()]
        if provides:
            row["provides"] = provides
        return row

    def requirement_row(self, requirement: dict) -> dict:
        key = requirement_node(requirement)
        status = self.reach.requirement_status(requirement, self.target)
        label = node_label(self.g, key) + (" (any)" if "category" in requirement else "")
        level = self._effect_level(requirement) if requirement["role"] == "effect" else self.levels.of(key)
        row = {"id": key, "label": label, "kind": "action" if ":" in key else self.g.kind(key), "role": requirement["role"],
               "status": status.label, "level": level}
        conditions = [describe_condition(self.g, c, self.target) for c in requirement.get("where", [])]
        if conditions:
            row["conditions"] = conditions
        reason = self._reason(requirement, status)
        if reason:
            row["reason"] = reason
        if requirement.get("notes"):
            row["notes"] = requirement["notes"].strip()
        return row

    def _effect_level(self, requirement: dict) -> int | None:
        """One above the easiest effect route that could meet this threshold (heat ≥ 1200 °C ranks above any fire)."""
        levels = [
            self.levels.routes[route_id] + 1
            for route_id in self.g.routes_achieving.get(requirement["effect"], [])
            if self.levels.routes.get(route_id) is not None and Tri.NO not in self._fits(route_id, requirement.get("where", []))
        ]
        return min(levels, default=None)

    def _fits(self, effect_route: str, where: list[dict]) -> list[Tri]:
        provides = self.g.routes[effect_route].get("provides", {})
        return [compare(provides.get(c["quantity"]), c["op"], condition_rhs(self.g, self.reach.quantities, c, self.target)) for c in where]

    def _reason(self, requirement: dict, status: Tri) -> str | None:
        role = requirement["role"]
        if role == "action":
            return None if status == Tri.YES else ("Might not be possible yet." if status == Tri.MAYBE else "Not reachable from the selection.")
        if role == "effect":
            return self._effect_reason(requirement, status)
        return self._thing_reason(requirement, status)

    def _thing_reason(self, requirement: dict, status: Tri) -> str | None:
        is_category = "category" in requirement
        candidates = [requirement["thing"]] if not is_category else sorted(self.g.members(requirement["category"]))
        where = requirement.get("where", [])
        reachable = [c for c in candidates if self.reach.status.get(c, Tri.NO) != Tri.NO]
        if status == Tri.YES:
            if not is_category:
                return None
            best = next(c for c in reachable if self._candidate_status(c, where) == Tri.YES)
            return f"Met by {self.g.label(best).lower()}."
        if status == Tri.MAYBE:
            unsure = next(c for c in reachable if self._candidate_status(c, where) == Tri.MAYBE)
            if self.reach.status[unsure] == Tri.MAYBE:
                return f"{self.g.label(unsure)} might not be reachable."
            return f"{self.g.label(unsure)}: {self._shortfalls(unsure, where, Tri.MAYBE)}."
        if not reachable:
            if not is_category:
                return "Not reachable from the selection."
            names = ", ".join(self.g.label(c).lower() for c in candidates[:4]) + (", …" if len(candidates) > 4 else "")
            return f"No member is reachable ({names})." if candidates else "No known members."
        return "; ".join(f"{self.g.label(c)}: {self._shortfalls(c, where, Tri.NO)}" for c in reachable[:3]) + "."

    def _candidate_status(self, candidate: str, where: list[dict]) -> Tri:
        return min([self.reach.status[candidate], *(self._compare(candidate, c) for c in where)])

    def _compare(self, candidate: str, condition: dict) -> Tri:
        have = self.reach.quantities.get(candidate, {}).get(condition["quantity"])
        return compare(have, condition["op"], condition_rhs(self.g, self.reach.quantities, condition, self.target))

    def _shortfalls(self, candidate: str, where: list[dict], outcome: Tri) -> str:
        """'hardness 2.5–3 Mohs; needs ≥ 6–7 Mohs (granite)' for each condition with the given outcome."""
        have = self.reach.quantities.get(candidate, {})
        conditions = [c for c in where if self._compare(candidate, c) == outcome]
        return self._gaps(have, conditions, "") or "doesn't qualify"

    def _gaps(self, have: dict, conditions: list[dict], prefix: str) -> str:
        """'hardness 2.5–3 Mohs; needs ≥ 6–7 Mohs (granite)', one clause per condition."""
        return "; ".join(
            f"{quantity_name(self.g, c['quantity']).lower()} {self._have(have, c['quantity'], prefix)}; "
            f"needs {describe_threshold(self.g, c, self.target)}"
            for c in conditions
        )

    def _have(self, have: dict, quantity: str, prefix: str) -> str:
        value = have.get(quantity)
        return "unknown" if value is None else prefix + quantity_value(self.g, quantity, value)

    def _effect_reason(self, requirement: dict, status: Tri) -> str | None:
        effect, where = requirement["effect"], requirement.get("where", [])
        sources = self.g.routes_achieving.get(effect, [])
        available = [rid for rid in sources if self.reach.route_status(rid, None) != Tri.NO]
        if status == Tri.YES:
            for route_id in available:
                if self.reach.route_status(route_id, None) == Tri.YES and all(f == Tri.YES for f in self._fits(route_id, where)):
                    return f"Met by {self.g.label(route_id).lower()}."
            return "Met by a level the selection implies."
        if status == Tri.MAYBE:
            return self._source_gaps(available, where, Tri.MAYBE, "Might not get there")
        if available:
            return self._source_gaps(available, where, Tri.NO, "Reachable sources are too weak")
        return f"No {self.g.label(effect).lower()} source is reachable."

    def _source_gaps(self, sources: list[str], where: list[dict], outcome: Tri, lead: str) -> str:
        """'Too weak: open fire (temperature up to 800 °C; needs ≥ 1100 °C).' for the sources with that outcome."""
        clauses = []
        for route_id in sources:
            fits = self._fits(route_id, where)
            if min(fits, default=Tri.YES) != outcome:
                # A source that clearly fails one condition can't "might" meet the requirement.
                continue
            conditions = [c for c, fit in zip(where, fits) if fit == outcome]
            if conditions:
                provides = self.g.routes[route_id].get("provides", {})
                clauses.append(f"{self.g.label(route_id).lower()} ({self._gaps(provides, conditions, 'up to ')})")
        return f"{lead}: {', '.join(clauses[:3])}." if clauses else f"{lead}."


_STATUS_RANK = {"no": 0, "maybe": 1, "yes": 2}


def _member_row(graph: Graph, levels: Levels, context: StatusContext, member: str) -> dict:
    return {"id": member, "label": graph.label(member), "kind": graph.kind(member), "status": context.status(member),
            "level": levels.of(member)}


def _ranked(levels: Levels, rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda row: levels.rank(row["id"], row["label"]))


def _all_dependencies(graph: Graph, levels: Levels, context: StatusContext, key: str, kind: str) -> dict:
    """Every certain need at every depth (the "Expand all dependencies" view)."""
    backward = Backward(graph)
    need = backward.of_action(*parse_action(key)) if kind == "action" else backward.of_thing(key)
    reach = context.reach
    rows = []
    for thing in need.things:
        rows.append((thing, graph.kind(thing), reach.status.get(thing, Tri.NO), None))
    for category in need.categories:
        best = max((reach.status.get(m, Tri.NO) for m in graph.members(category)), default=Tri.NO)
        rows.append((category, "category", best, None))
    for action in need.actions:
        rows.append((action_key(action), "action", reach.action_status(*action), None))
    for effect, bounds in need.effects.items():
        where = [{"quantity": q, "op": op, "value": value} for q, (op, value) in sorted(bounds.items())]
        conditions = [describe_condition(graph, c) for c in where]
        rows.append((effect, "effect", reach.effect_status(effect, where, None), conditions))
    buckets: dict[str, list[dict]] = {"missing": [], "uncertain": [], "have": []}
    bucket_of = {Tri.NO: "missing", Tri.MAYBE: "uncertain", Tri.YES: "have"}
    for row_id, row_kind, status, conditions in rows:
        row = {"id": row_id, "label": node_label(graph, row_id), "kind": row_kind, "status": status.label, "level": levels.of(row_id)}
        if conditions:
            row["conditions"] = conditions
        buckets[bucket_of[status]].append(row)
    return {name: _ranked(levels, items) for name, items in buckets.items()}
