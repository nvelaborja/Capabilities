"""Pleiades' ancient mines and quarries as occurrences (ADR 0046).

`upstream_built_dir` (conftest) is the repository's graph built from samples of every dataset, Pleiades' being thirteen
real places that cover each case; `built_dir` and `graph` are built from the cold backups: every Pleiades place.
"""

import pytest

from capabilities.built import load_occurrences, load_queue
from capabilities_pipeline.build import BuildError, build


def occurrences_of(build_dir, name: str) -> dict[str, dict]:
    """The Pleiades place's occurrences, by the source or class they belong to."""
    return {row["source_id"]: row for row in load_occurrences(build_dir) if row["dataset"] == "pleiades" and row["name"] == name}


class TestDownload:
    def test_the_daily_dump_is_kept_as_published(self, tmp_path, pleiades_gz):
        from capabilities_pipeline.upstream import PLEIADES, fetch

        snapshot = fetch(PLEIADES, tmp_path, pleiades_gz)
        assert snapshot["rows"] == 13
        assert snapshot["license"].startswith("CC BY 3.0")


class TestMatching:
    def test_a_copper_mine_is_a_place_of_both_copper_ore_classes_since_its_ore_isnt_recorded(self, upstream_built_dir):
        agrokipia = occurrences_of(upstream_built_dir, "Agrokipia")
        assert set(agrokipia) == {"copper-ore", "copper-sulphide-ore"}
        assert agrokipia["copper-ore"]["matched_on"] == "tag: copper"

    def test_a_material_named_only_in_the_description_matches_too(self, upstream_built_dir):
        # given: "Bronze Age copper mine reused as a sanctuary", with no tags
        assert occurrences_of(upstream_built_dir, "Chale Ghar 1")["copper-ore"]["matched_on"] == "text: copper"
        assert set(occurrences_of(upstream_built_dir, "As Muradellas Mine")) == {"tin-ore"}

    def test_the_iron_age_is_a_date_not_an_iron_mine(self, upstream_built_dir):
        # given: Almyras, a copper site whose description says its remains are "dated to the Iron Age"
        assert set(occurrences_of(upstream_built_dir, "Almyras")) == {"copper-ore", "copper-sulphide-ore"}

    def test_each_metal_of_a_mine_matches_its_own_rule_and_the_rest_are_left(self, upstream_built_dir):
        # given: Dognecea, a mine of copper, gold, iron and silver; we have no source of gold or silver
        assert set(occurrences_of(upstream_built_dir, "Dognecea")) == {"copper-ore", "copper-sulphide-ore", "iron-ore"}

    def test_quarries_are_places_of_our_stone_sources(self, upstream_built_dir):
        assert set(occurrences_of(upstream_built_dir, "Aswan Quarry Landscape")) == {"granite-outcrop"}
        assert set(occurrences_of(upstream_built_dir, "Roman quarry of Antas")) == {"limestone-outcrop"}
        assert set(occurrences_of(upstream_built_dir, "Grimes Graves")) == {"flint-deposit"}

    @pytest.mark.parametrize("name", ["Athenae", "Antonianum Metallum", "Gold Mines at Dolaucothi, Wales"])
    def test_settlements_unlocated_places_and_unmatched_mines_are_not_placed(self, upstream_built_dir, name):
        assert occurrences_of(upstream_built_dir, name) == {}


class TestWhatAPlaceSays:
    def test_an_ancient_working_was_worked_and_says_when_it_is_attested(self, upstream_built_dir):
        agrokipia = occurrences_of(upstream_built_dir, "Agrokipia")["copper-ore"]
        assert (agrokipia["state"], agrokipia["worked_by_year"]) == ("worked", None)
        assert (agrokipia["attested_from"], agrokipia["attested_to"]) == (-750, 300)
        assert list(agrokipia["periods"]) == ["archaic", "classical", "hellenistic-republican", "roman"]
        assert agrokipia["url"] == "https://pleiades.stoa.org/places/707452"

    def test_a_rough_location_is_marked_approximate_and_mrds_doesnt_say(self, upstream_built_dir):
        assert occurrences_of(upstream_built_dir, "Temesa Copper Mines")["copper-ore"]["approximate"] is True
        assert occurrences_of(upstream_built_dir, "Agrokipia")["copper-ore"]["approximate"] is False
        assert {row["approximate"] for row in load_occurrences(upstream_built_dir) if row["dataset"] == "mrds"} == {None}

    def test_a_place_attested_only_in_modern_times_stays_since_the_material_was_there(self, graph, built_dir):
        # given: Bou Khenndak Copper Mines, attested AD 2000-2099 only
        (place,) = [row for row in load_occurrences(built_dir) if row["name"] == "Bou Khenndak Copper Mines"
                    and row["source_id"] == "copper-ore"]
        assert (place["state"], place["attested_from"]) == ("worked", 2000)


class TestCurationQueue:
    def test_unmatched_mines_and_quarries_are_queued_by_the_material_they_name_last_of_all(self, upstream_built_dir):
        queue = load_queue(upstream_built_dir)
        unmatched = {item["label"]: item["priority"] for item in queue if item["kind"] == "unmatched_place"}
        # Dolaucothi names gold; the untitled rough quarry names nothing.
        assert unmatched == {"Gold": 1, "No material named": 1}
        assert queue[-1]["kind"] == "unmatched_place"


class TestCuration:
    def test_a_suppressed_place_is_left_out_and_isnt_queued_as_unmatched(self, data_copy, tmp_path):
        # given: Agrokipia (copper) and Dolaucothi (gold, unmatched) suppressed
        suppressions = data_copy / "data" / "suppressions" / "suppressed_records.csv"
        suppressions.write_text(
            suppressions.read_text() + "pleiades,707452,Testing a suppression.\npleiades,82301,Testing a suppression.\n",
            encoding="utf-8",
        )
        build(data_copy, tmp_path / "build")
        assert not [row for row in load_occurrences(tmp_path / "build") if row["record_id"] in ("707452", "82301")]
        # then: it was looked at, so it isn't a gap either
        gold = next(item for item in load_queue(tmp_path / "build") if item["subject"] == "pleiades:gold")
        assert gold["priority"] == 99  # 100 gold mines and quarries on 2026-11-24, less Dolaucothi

    def test_a_rule_may_only_place_at_a_source_or_a_class(self, data_copy, tmp_path):
        rules = data_copy / "data" / "crosswalks" / "pleiades_sources.csv"
        rules.write_text(rules.read_text() + "malachite,mine,copper,A material can't have places.\n", encoding="utf-8")
        with pytest.raises(BuildError, match="pleiades_rules_target_sources_or_classes"):
            build(data_copy, tmp_path / "build")


@pytest.fixture(scope="module")
def places(built_dir):
    """Every occurrence of the repository's graph, from the cold backups."""
    from capabilities.places import Places

    return Places.from_rows(load_occurrences(built_dir), {"pleiades_places": {"retrieved_at": "2026-11-24T17:34:07Z"}})


class TestOnTheMap:
    def test_a_mineral_shows_its_classes_ancient_mines_marked_as_such(self, graph, places):
        from capabilities.places import places_view

        view = places_view(graph, places, "malachite")
        copper = next(source for source in view["sources"] if source["id"] == "copper-ore")
        assert copper["class_level"] is True and copper["places"] > 100
        features = view["features"]["features"]
        assert any(f["properties"]["class_level"] for f in features)
        assert not any(f["properties"]["class_level"] for f in features if f["properties"]["dataset"] == "mrds")

    def test_the_sulphides_show_the_copper_mines_too(self, graph, places):
        from capabilities.places import places_view

        sources = [source["id"] for source in places_view(graph, places, "chalcopyrite")["sources"]]
        assert sources == ["chalcopyrite-deposit", "copper-sulphide-ore"]

    def test_a_produced_material_has_no_places_even_in_a_class_that_has(self, graph, places):
        from capabilities.places import places_view

        assert places_view(graph, places, "roasted-copper-ore")["sources"] == []
