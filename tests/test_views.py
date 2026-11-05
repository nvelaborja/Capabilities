import pytest

from capabilities.levels import compute_levels
from capabilities.reasoner import Selection, explore
from capabilities.views import StatusContext, UnknownNode, explain, explore_view, graph_view, implied_by


def egypt(graph) -> Selection:
    return Selection.from_profile(graph.profiles["middle-kingdom-egypt"])


@pytest.fixture(scope="module")
def levels(graph):
    return compute_levels(graph)


def context_for(graph, selected: Selection, hypothetical: Selection = Selection()) -> StatusContext:
    return StatusContext.from_explore(graph, explore(graph, selected, hypothetical))


def requirement(view: dict, route_id: str, node_id: str) -> dict:
    route = next(r for r in view["routes"] if r["id"] == route_id)
    return next(row for row in route["requirements"] if row["id"] == node_id)


class TestGraphView:
    def test_every_edge_connects_drawn_nodes(self, graph, levels):
        view = graph_view(graph, levels)
        ids = {node["id"] for node in view["nodes"]}
        assert all(edge["source"] in ids and edge["target"] in ids for edge in view["edges"])

    def test_techniques_are_listed_but_not_drawn(self, graph, levels):
        view = graph_view(graph, levels)
        assert "iron-smelting" not in {node["id"] for node in view["nodes"]}
        assert "iron-smelting" in {technique["id"] for technique in view["techniques"]}

    @pytest.mark.parametrize(("node_id", "selectable"), [("steel", True), ("cut:wood", True), ("iron-ore", False), ("heat", False)])
    def test_only_concrete_things_and_actions_are_selectable(self, graph, levels, node_id, selectable):
        nodes = {node["id"]: node for node in graph_view(graph, levels)["nodes"]}
        assert nodes[node_id]["selectable"] is selectable

    def test_routes_are_junctions_between_a_thing_and_its_requirements(self, graph, levels):
        # given: steel has two routes, and the bloomery route needs heat at a stated threshold
        edges = graph_view(graph, levels)["edges"]
        into_steel = {e["source"] for e in edges if e["target"] == "steel" and e["kind"] == "produces"}
        heat_edge = next(e for e in edges if e["source"] == "heat" and e["target"] == "bloomery-smelting")
        # then: two junctions produce steel, and the heat edge carries a readable threshold
        assert into_steel == {"steel-by-carburizing", "steel-by-crucible"}
        assert heat_edge["label"] == "Temperature ≥ 1100 °C · Duration ≥ 2 hours"

    def test_routes_carry_their_level_except_verb_routes(self, graph, levels):
        nodes = {node["id"]: node for node in graph_view(graph, levels)["nodes"]}
        assert nodes["bloomery-smelting"]["level"] == levels.of("bloom-iron") - 1
        assert nodes["cut-abrasive-saw"]["level"] is None

    def test_extra_actions_are_drawn_and_connected_to_their_verb_routes(self, graph, levels):
        # given: nothing in the data references cut:limestone
        before = graph_view(graph, levels)
        after = graph_view(graph, levels, [("cut", "limestone")])
        # then: it appears only on request, with the routes that can perform it (chopping is for plant material only)
        assert "cut:limestone" not in {n["id"] for n in before["nodes"]}
        performers = {e["source"] for e in after["edges"] if e["target"] == "cut:limestone"}
        assert {"cut-abrasive-saw", "cut-by-chiseling"} <= performers
        assert "cut-by-chopping" not in performers


class TestStatuses:
    @pytest.mark.parametrize(("node_id", "status"), [
        ("copper", "selected"),          # in the profile
        ("cut:granite", "selected"),     # an action in the profile
        ("crucible", "implied"),         # every route to tin bronze needs one
        ("cut:wood", "implied"),
        ("heat", "implied"),
        ("bellows", "reachable"),
        ("bloom-iron", "near"),          # one ingredient (iron ore) away
        ("iron-ore", "out"),
        ("diamond-saw", "out"),
    ])
    def test_middle_kingdom_egypt(self, graph, node_id, status):
        assert context_for(graph, egypt(graph)).status(node_id) == status

    def test_hypotheticals_are_marked_and_unlock_steel(self, graph):
        context = context_for(graph, egypt(graph), Selection.parse(["hematite"]))
        assert context.status("hematite") == "hypothetical"
        assert context.status("steel") == "reachable"

    def test_explore_view_has_a_status_for_every_drawn_node(self, graph, levels):
        view = explore_view(graph, explore(graph, egypt(graph)))
        drawn = {n["id"] for n in graph_view(graph, levels)["nodes"] if n["kind"] != "route"}
        assert drawn <= set(view["status"])
        assert set(view["route_status"]) == set(graph.routes)
        assert view["route_status"]["bloomery-smelting"] == "no"


class TestExploreViewExtras:
    def test_implied_effects_are_readable(self, graph):
        view = explore_view(graph, explore(graph, egypt(graph)))
        assert view["implied_effects"] == [{"id": "heat", "label": "Heat", "conditions": ["Temperature ≥ 1085 °C"]}]

    def test_near_misses_are_grouped_by_thing_and_name_what_is_missing(self, graph):
        near = {item["id"]: item for item in explore_view(graph, explore(graph, egypt(graph)))["near"]}
        assert near["bloom-iron"]["routes"][0]["missing"] == {"id": "iron-ore", "label": "Iron ore (any)", "kind": "category"}
        assert {r["id"] for r in near["steel"]["routes"]} == {"steel-by-carburizing", "steel-by-crucible"}

    def test_warnings_use_names_not_ids(self, graph):
        warnings = explore_view(graph, explore(graph, egypt(graph)))["warnings"]
        assert warnings == ["Implies access to some tin ore (cassiterite); all known sources are regional, so it may have been traded."]


class TestImpliedBy:
    def test_names_the_selections_that_imply_each_item(self, graph):
        found = implied_by(graph, egypt(graph))
        assert "tin-bronze" in found["crucible"]
        assert found["tin-ore"] == ["tin-bronze"]

    def test_actions_can_imply_things(self, graph):
        found = implied_by(graph, Selection.parse(["drill:granite"]))
        assert "drill:granite" in found["cut:wood"]


class TestExplain:
    def test_shows_first_degree_requirements_per_route(self, graph, levels):
        # given: Middle Kingdom Egypt and steel, which is out of reach
        view = explain(graph, levels, context_for(graph, egypt(graph)), "steel")
        # then: each route lists only its direct requirements, missing ones first
        assert {r["id"] for r in view["routes"]} == {"steel-by-carburizing", "steel-by-crucible"}
        for route in view["routes"]:
            assert route["requirements"][0]["id"] == "bloom-iron"
            assert route["requirements"][0]["status"] == "no"
            assert "iron-ore" not in {row["id"] for row in route["requirements"]}  # two levels down
        assert "all" not in view

    def test_routes_with_fewer_missing_requirements_come_first(self, graph, levels):
        # given: four ways to cut wood; only the diamond saw is missing something outright
        view = explain(graph, levels, context_for(graph, egypt(graph)), "cut:wood")
        # then: fewest missing first, then fewest uncertain, then by name (not plain alphabetical order)
        assert [(r["id"], r["missing"], r["uncertain"]) for r in view["routes"]] == [
            ("cut-by-chopping", 0, 0), ("cut-abrasive-saw", 0, 1), ("cut-by-chiseling", 0, 1), ("cut-diamond-saw", 1, 0),
        ]

    def test_requirements_list_missing_first_then_by_tech_level(self, graph, levels):
        # given: alloying bronze needs tin (missing), heat ≥ 1085 °C (a furnace), a crucible and copper
        view = explain(graph, levels, context_for(graph, egypt(graph)), "tin-bronze")
        route = next(r for r in view["routes"] if r["id"] == "bronze-by-alloying")
        # then: the missing tin leads, then the met ones from most to least advanced
        assert [row["id"] for row in route["requirements"]] == ["tin", "heat", "crucible", "copper"]

    def test_missing_requirements_lead_even_when_primitive(self, graph, levels):
        # given: smelting needs iron ore (level 0, missing) plus heat, charcoal and a furnace (higher levels, met)
        view = explain(graph, levels, context_for(graph, egypt(graph)), "bloom-iron")
        rows = view["routes"][0]["requirements"]
        assert [row["id"] for row in rows] == ["iron-ore", "heat", "charcoal", "bloomery-furnace"]

    def test_heat_rows_rank_by_the_threshold_they_need(self, graph, levels):
        # given: carburizing needs ≥ 900 °C (any fire would do at that level) and crucible steel ≥ 1200 °C (a furnace)
        view = explain(graph, levels, context_for(graph, egypt(graph)), "steel")
        cool = requirement(view, "steel-by-carburizing", "heat")
        hot = requirement(view, "steel-by-crucible", "heat")
        assert hot["level"] > levels.of("heat")
        assert hot["conditions"] == ["Temperature ≥ 1200 °C", "Duration ≥ 24 hours"]
        assert cool["status"] == "yes"

    @pytest.mark.parametrize(("node", "route_id", "row_id", "status", "reason"), [
        ("steel", "steel-by-carburizing", "carbon-source", "yes", "Met by charcoal."),
        ("bloom-iron", "bloomery-smelting", "iron-ore", "no", "No member is reachable (hematite, limonite (bog iron ore))."),
        ("cut:granite", "cut-by-chiseling", "chisel", "no", "Copper chisel: hardness 2.5–3 Mohs; needs ≥ 6–7 Mohs (granite)."),
        ("shape:limestone", "shape-by-pounding", "pounder", "maybe",
         "Dolerite pounder: fracture toughness unknown; needs ≥ 0.62–0.68 MPa·√m (limestone)."),
        ("steel", "steel-by-crucible", "heat", "maybe",
         "Might not get there: charcoal furnace with forced draft (temperature up to 1100–1250 °C; needs ≥ 1200 °C)."),
    ])
    def test_reasons_say_why(self, graph, levels, node, route_id, row_id, status, reason):
        row = requirement(explain(graph, levels, context_for(graph, egypt(graph)), node), route_id, row_id)
        assert (row["status"], row["reason"]) == (status, reason)

    def test_too_weak_heat_sources_are_named(self, workshop):
        # given: nothing selected, so flint (regional) is missing and only the open fire is reachable
        levels = compute_levels(workshop)
        view = explain(workshop, levels, context_for(workshop, Selection()), "metal")
        row = requirement(view, "smelt-metal", "heat")
        assert row["reason"] == "Reachable sources are too weak: open fire (temperature up to 600–800 °C; needs ≥ 1000 °C)."

    def test_drill_down_works_on_categories(self, graph, levels):
        view = explain(graph, levels, context_for(graph, egypt(graph)), "iron-ore")
        assert [(m["id"], m["status"]) for m in view["members"]] == [("hematite", "out"), ("limonite", "out")]

    def test_expand_all_lists_every_certain_need_by_level(self, graph, levels):
        view = explain(graph, levels, context_for(graph, egypt(graph)), "steel", everything=True)
        missing = [row["id"] for row in view["all"]["missing"]]
        have = [row["level"] for row in view["all"]["have"]]
        assert missing == ["bloom-iron", "iron-ore"]  # level 7 before level 0
        assert have == sorted(have, reverse=True)

    @pytest.mark.parametrize("node", ["iron-smelting", "unobtainium", "fly:granite", "cut:moonrock"])
    def test_rejects_what_it_cannot_explain(self, graph, levels, node):
        with pytest.raises(UnknownNode):
            explain(graph, levels, context_for(graph, Selection()), node)
