from capabilities.levels import Levels, compute_levels


class TestLevelsOnASmallGraph:
    def test_natural_materials_are_level_zero(self, workshop):
        # given: wood (ubiquitous), flint and granite (regional)
        # when: computing levels
        levels = compute_levels(workshop)
        # then: all natural materials are primitives, regardless of where they occur
        assert [levels.of(m) for m in ("wood", "flint", "granite")] == [0, 0, 0]

    def test_a_thing_is_one_step_above_its_easiest_route(self, workshop):
        # given: ember can come from charcoal (level 3) or from wood + a knife (level 1)
        levels = compute_levels(workshop)
        # then: the easier route decides, and charcoal sits above ember
        assert levels.of("knife") == 1
        assert levels.of("ember") == 2
        assert levels.of("charcoal") == 3

    def test_effect_requirements_use_the_easiest_source_that_meets_the_threshold(self, workshop):
        # given: an open fire (≤ 800 °C, level 0 route) and a furnace (1200 °C, burns level-3 charcoal)
        levels = compute_levels(workshop)
        # then: the pot (≥ 500 °C) needs only the fire; the metal (≥ 1000 °C) needs the furnace
        assert levels.of("pot") == 2
        assert levels.of("metal") == 5
        assert levels.routes["furnace"] == 3

    def test_a_category_takes_its_lowest_member(self, workshop):
        assert compute_levels(workshop).of("blade") == 1

    def test_actions_only_count_tools_that_could_meet_the_target_condition(self, workshop):
        # given: the only blade (a knife, hardness 5) can cut wood (2) but not granite (6–7)
        levels = compute_levels(workshop)
        # then: cutting wood is one step above the knife, and cutting granite has no level
        assert levels.of("cut:wood") == 2
        assert levels.of("cut:granite") is None

    def test_things_without_a_route_have_no_level(self, workshop):
        assert compute_levels(workshop).of("relic") is None

    def test_techniques_get_no_level(self, workshop):
        assert "knapping" not in compute_levels(workshop).levels


class TestRanking:
    def test_highest_level_first_and_unknown_levels_last(self, workshop):
        levels = compute_levels(workshop)
        items = ["wood", "relic", "metal", "knife"]
        assert sorted(items, key=lambda i: levels.rank(i, i)) == ["metal", "knife", "wood", "relic"]

    def test_ties_go_to_more_certain_prerequisites_then_label(self):
        # given: three items at the same level; "broad" certainly needs more than the other two
        levels = Levels({"broad": 2, "alpha": 2, "beta": 2}, {"broad": 5, "alpha": 1, "beta": 1}, {})
        # when: ranking them
        ranked = sorted(["beta", "alpha", "broad"], key=lambda i: levels.rank(i, i))
        # then: more prerequisites first, then alphabetical
        assert ranked == ["broad", "alpha", "beta"]

    def test_an_explicit_level_overrides_the_nodes_own(self, workshop):
        levels = compute_levels(workshop)
        assert levels.rank("heat", "Heat", level=7) < levels.rank("metal", "Metal")


class TestLevelsOnTheRealGraph:
    def test_the_iron_chain_climbs(self, graph):
        levels = compute_levels(graph)
        assert levels.of("deadwood") == 0
        assert 0 < levels.of("bloom-iron") < levels.of("steel") < levels.of("hardened-steel")

    def test_felling_and_cutting_timber_need_a_knapped_tool(self, graph):
        # given: felling and chopping need an edged tool, and the stone chopper is knapped from fieldstone
        levels = compute_levels(graph)
        assert levels.of("stone-chopper") == 1
        assert levels.of("timber") == levels.of("cut:timber") == 2

    def test_sources_and_hand_gathered_materials_start_at_zero(self, graph):
        levels = compute_levels(graph)
        assert [levels.of(t) for t in ("standing-trees", "granite-outcrop", "deadwood", "fieldstone")] == [0, 0, 0, 0]

    def test_modern_things_without_routes_have_no_level(self, graph):
        assert compute_levels(graph).of("diamond-saw") is None
