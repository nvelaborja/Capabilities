import pytest

from capabilities.reasoner import (
    Backward,
    Necessity,
    Reachability,
    Selection,
    assess_job,
    closure,
    explore,
    need_tree,
)
from capabilities.graph import Graph
from capabilities.tristate import Tri


@pytest.fixture
def tiny_graph(tmp_path) -> Graph:
    """A minimal graph with no heat routes, to test implied effect levels in isolation."""
    def needs_heat(route_id, output, temperature, extra=()):
        return {"id": route_id, "kind": "route", "label": route_id, "achieves": {"thing": output},
                "requires": [*extra, {"role": "effect", "effect": "heat",
                                      "where": [{"quantity": "temperature_c", "op": ">=", "value": temperature}]}],
                "outputs": [{"thing": output}], "references": []}
    ore = {"role": "consumed", "thing": "ore"}
    return Graph(
        tmp_path,
        quantities={"temperature_c": {"id": "temperature_c", "kind": "quantity", "unit": "°C"}},
        things={
            "heat": {"id": "heat", "kind": "effect", "label": "Heat", "dimensions": ["temperature_c"]},
            "ore": {"id": "ore", "kind": "material", "label": "Ore", "origin": "natural", "availability": "regional"},
            "pot": {"id": "pot", "kind": "artifact", "label": "Pot"},
            "soft-metal": {"id": "soft-metal", "kind": "material", "label": "Soft metal", "origin": "produced"},
            "hard-metal": {"id": "hard-metal", "kind": "material", "label": "Hard metal", "origin": "produced"},
        },
        routes={
            "fire-pot": needs_heat("fire-pot", "pot", 1100),
            "smelt-soft": needs_heat("smelt-soft", "soft-metal", 1000, [ore]),
            "smelt-hard": needs_heat("smelt-hard", "hard-metal", 1200, [ore]),
        },
    )


def egypt(graph) -> Selection:
    return Selection.from_profile(graph.profiles["middle-kingdom-egypt"])


def walk(node: dict):
    """Every node in a need tree."""
    yield node
    for route in node.get("routes", []):
        for requirement in route["requires"]:
            yield from walk(requirement)


class TestSelection:
    def test_parses_things_and_actions(self):
        # given: a mix of thing ids and verb:target actions
        # when: parsing them
        selection = Selection.parse(["copper", "cut:granite"])
        # then: they are separated
        assert selection.things == {"copper"}
        assert selection.actions == {("cut", "granite")}

    def test_reports_unknown_items(self, graph):
        selection = Selection.parse(["copper", "unobtainium", "fly:granite", "cut:moonrock"])
        assert selection.unknown_ids(graph) == ["cut:moonrock (unknown target)", "fly:granite (unknown verb)", "unobtainium"]


class TestNecessityMerging:
    def test_keeps_weakest_shared_lower_bound(self):
        # given: two alternative routes that need heat at different temperatures and durations
        hot_short = Necessity(effects={"heat": {"temperature_c": (">=", 1200), "duration_h": (">=", 1)}})
        cool_long = Necessity(effects={"heat": {"temperature_c": (">=", 900), "duration_h": (">=", 24)}})
        # when: finding what both routes certainly need
        common = Necessity.common([hot_short, cool_long])
        # then: the weakest bound on each quantity is kept
        assert common.effects == {"heat": {"temperature_c": (">=", 900), "duration_h": (">=", 1)}}

    def test_drops_quantities_not_constrained_by_every_route(self):
        with_duration = Necessity(effects={"heat": {"temperature_c": (">=", 1000), "duration_h": (">=", 5)}})
        without_duration = Necessity(effects={"heat": {"temperature_c": (">=", 1100)}})
        common = Necessity.common([with_duration, without_duration])
        assert common.effects == {"heat": {"temperature_c": (">=", 1000)}}

    def test_within_one_route_the_strongest_bound_wins(self):
        need = Necessity(effects={"heat": {"temperature_c": (">=", 900)}})
        need.add_all(Necessity(effects={"heat": {"temperature_c": (">=", 1100)}}))
        assert need.effects["heat"]["temperature_c"] == (">=", 1100)


class TestBackward:
    def test_steel_certainly_needs_bloomery_iron_and_its_inputs(self, graph):
        # given: steel, which has a carburizing route and a crucible route
        # when: asking what every route needs
        certain = Backward(graph).of_thing("steel")
        # then: both routes share the bloomery chain
        assert {"bloom-iron", "bloomery-furnace", "charcoal", "clay", "wood"} <= certain.things
        assert {"iron-ore", "carbon-source"} <= certain.categories
        assert ("cut", "wood") in certain.actions
        # and the merged heat need is the weakest common bound: 1100 °C (bloomery) and 24 h (both steel routes)
        assert certain.effects["heat"] == {"temperature_c": (">=", 1100), "duration_h": (">=", 24)}

    def test_no_route_needs_1370_degrees(self, graph):
        certain = Backward(graph).of_thing("steel")
        assert certain.effects["heat"]["temperature_c"][1] < 1370

    def test_bronze_does_not_prove_tin_smelting(self, graph):
        # given: tin bronze can be made from tin metal or directly from tin ore
        certain = Backward(graph).of_thing("tin-bronze")
        # then: tin metal is not certain, but copper, a crucible, and heat to melt copper are
        assert "tin" not in certain.things
        assert {"copper", "crucible"} <= certain.things
        assert certain.effects["heat"]["temperature_c"] == (">=", 1085)

    def test_handles_cycles(self, graph):
        # given: heat needs charcoal, and charcoal needs heat to light the clamp
        # when / then: backward inference terminates
        assert Backward(graph).of_thing("charcoal").things >= {"wood"}


class TestNeedTree:
    def test_effects_expand_into_routes_that_can_deliver_them(self, graph):
        # given: copper smelting needs heat of at least 1085 °C
        tree = need_tree(graph, "copper")
        heat = next(n for n in walk(tree) if n.get("type") == "effect")
        # then: only the furnace is shown; the open fire and fire piston are flagged as too weak
        assert [route["id"] for route in heat["routes"]] == ["heat-forced-draft-furnace"]
        assert set(heat["too_weak"]) == {"heat-open-fire", "heat-fire-piston"}

    def test_wood_cutting_is_a_common_ancestor(self, graph):
        tree = need_tree(graph, "steel-spear")
        assert any(node["id"] == "cut:wood" for node in walk(tree))

    def test_actions_can_be_asked_about(self, graph):
        tree = need_tree(graph, "cut:granite")
        assert tree["type"] == "action"
        assert "cut-by-chopping" not in [route["id"] for route in tree["routes"]]  # only applies to plant material


class TestReachability:
    def test_know_how_never_gates(self, graph):
        # given: only bog iron ore (plus the free ubiquitous materials)
        reach = Reachability(graph, Selection.parse(["limonite"]))
        # then: iron and steel are reachable even though nobody selected smelting know-how
        assert reach.status["bloom-iron"] == Tri.YES
        assert reach.status["steel"] == Tri.YES

    def test_regional_materials_are_not_free(self, graph):
        reach = Reachability(graph, Selection())
        assert reach.status["bloom-iron"] == Tri.NO
        assert reach.status["stone-chopper"] == Tri.YES  # fieldstone and wood are ubiquitous

    def test_fire_piston_is_too_weak_for_smelting(self, graph):
        # given: bloomery smelting needs at least 1100 °C held for at least 2 hours
        tree = need_tree(graph, "bloom-iron")
        heat = next(n for n in walk(tree) if n.get("type") == "effect" and n.get("where"))
        # then: a fire piston's brief, tiny spike of heat is excluded as a way to meet it
        assert "heat-fire-piston" in heat["too_weak"]
        assert "heat-fire-piston" not in [route["id"] for route in heat["routes"]]

    def test_copper_chisel_on_limestone_is_maybe(self, graph):
        # given: copper (Mohs 2.5–3) and limestone (Mohs 3)
        reach = Reachability(graph, Selection.parse(["copper-chisel"]))
        # then: chiseling limestone is "maybe" and granite is "no"
        assert reach.route_status("cut-by-chiseling", "limestone") == Tri.MAYBE
        assert reach.route_status("cut-by-chiseling", "granite") == Tri.NO

    def test_selected_actions_count_as_done(self, graph):
        reach = Reachability(graph, Selection.parse(["shape:granite"]))
        assert reach.action_status("shape", "granite") == Tri.YES

    def test_implied_effect_levels_are_usable(self, tiny_graph):
        # given: a graph with no way to make heat, where making a pot implies reaching 1100 °C
        # when: a group is known to have made pots
        implied, reach = closure(tiny_graph, Selection.parse(["pot", "ore"]))
        # then: they reached 1100 °C, so a metal needing 1000 °C is reachable, but one needing 1200 °C is not
        assert implied.effects == {"heat": {"temperature_c": (">=", 1100)}}
        assert reach.status["soft-metal"] == Tri.YES
        assert reach.status["hard-metal"] == Tri.NO


class TestExplore:
    def test_separates_selected_implied_and_reachable(self, graph):
        result = explore(graph, egypt(graph))
        assert "copper-saw" in result.selected.things
        assert "crucible" in result.implied.things
        assert "copper-saw" not in result.reachable
        assert "charcoal" in result.reachable

    def test_iron_is_one_ingredient_away_for_egypt(self, graph):
        result = explore(graph, egypt(graph))
        assert {"thing": "bloom-iron", "route": "bloomery-smelting", "missing": "consumed iron-ore (any)"} in result.near_misses

    def test_hypothetical_iron_ore_unlocks_steel(self, graph):
        result = explore(graph, egypt(graph), Selection.parse(["hematite"]))
        assert {"steel", "steel-chisel", "hardened-steel"} <= set(result.reachable)
        assert result.hypothetical.things == {"hematite"}

    def test_warns_about_imported_tin(self, graph):
        result = explore(graph, egypt(graph))
        assert any("tin ore (cassiterite)" in warning for warning in result.warnings)

    def test_reports_target_independent_verbs_once(self, graph):
        result = explore(graph, egypt(graph))
        assert result.actions["move"] == {"(any)": "yes"}
        assert result.actions["cut"]["granite"] == "yes"
        assert "water" not in result.actions["cut"]


class TestFeasibility:
    def assess(self, graph, job_id, hypothetical=()):
        _, reach = closure(graph, egypt(graph), Selection.parse(hypothetical))
        return assess_job(graph, graph.jobs[job_id], reach)

    def test_granite_saw_cut_takes_weeks_to_months(self, graph):
        # given: one 2 m x 1 m saw cut, using Stocks's measured 12–24 cm³/h
        result = self.assess(graph, "granite-slab-saw-cut")
        saw = next(r for r in result.steps[0].routes if r.route == "cut-abrasive-saw")
        # then: 12,000–20,000 cm³ takes 500–1,667 hours, and precision is unknown
        assert saw.hours == pytest.approx((500, 1666.67), rel=1e-3)
        assert saw.duration_bands == ("weeks", "months")
        assert saw.verdict == "insufficient data"

    def test_copper_chisel_cannot_cut_granite(self, graph):
        result = self.assess(graph, "granite-slab-saw-cut")
        chisel = next(r for r in result.steps[0].routes if r.route == "cut-by-chiseling")
        assert chisel.verdict == "not available"

    def test_diamond_saw_only_as_hypothetical(self, graph):
        without = self.assess(graph, "granite-slab-saw-cut")
        with_saw = self.assess(graph, "granite-slab-saw-cut", ["diamond-saw"])
        route = lambda result: next(r for r in result.steps[0].routes if r.route == "cut-diamond-saw")
        assert route(without).verdict == "not available"
        assert route(with_saw).available == Tri.YES

    def test_pounding_scales_with_workers(self, graph):
        # given: 1 m³ of granite, 216 cm³/h per pounder, 20 pounders at once
        result = self.assess(graph, "pound-granite-cubic-metre")
        pounding = result.steps[0].best
        # then: about 231 hours, uncertain only because dolerite's toughness is not sourced yet
        assert pounding.units == 20
        assert pounding.hours[0] == pytest.approx(1_000_000 / 216 / 20)
        assert pounding.verdict == "uncertain"
        assert "toughness" in pounding.reasons[0]

    def test_pounding_alone_cannot_reach_fine_precision(self, graph):
        # given: the pounding job, but now requiring about 1 mm precision
        job = {**graph.jobs["pound-granite-cubic-metre"], "limits": {"max_crew": 20, "max_units": 20, "precision": "P2"}}
        _, reach = closure(graph, egypt(graph))
        result = assess_job(graph, job, reach)
        # then: pounding is ruled out on precision, not on time
        assert result.steps[0].best.verdict == "no known route meets these constraints"
        assert "P2 is required" in result.steps[0].best.reasons[0]

    def test_time_budget_uses_the_generous_end(self, graph):
        job = {**graph.jobs["pound-granite-cubic-metre"], "limits": {"max_crew": 20, "max_units": 20, "max_duration_h": 100}}
        _, reach = closure(graph, egypt(graph))
        result = assess_job(graph, job, reach)
        assert result.verdict == "no known route meets these constraints"

    def test_multi_step_job_reports_missing_finishing_data(self, graph):
        result = self.assess(graph, "granite-box-rough-and-finish")
        assert [s.best.route for s in result.steps] == ["shape-by-pounding", "finish-abrasive-grinding"]
        assert result.steps[0].best.hours[0] == pytest.approx(2_000_000 / 216 / 4)
        assert result.verdict == "insufficient data"
        assert result.total_hours is None  # the grinding step has no rate yet
