"""Upstream ore minerals as nodes, roasting, and the curation queue (ADR 0045).

`graph` and `built_dir` (conftest) are the repository's graph built from the cold backups: real MRDS and Wikidata data.
"""

import pytest

from capabilities.built import load_queue
from capabilities.reasoner import Selection, explore
from capabilities_pipeline.build import BuildError, build


class TestOreMineralNodes:
    def test_a_mineral_is_a_material_in_its_ore_class_named_and_described_from_wikidata(self, graph):
        azurite = graph.things["azurite"]
        assert (azurite["kind"], azurite["label"], azurite["origin"], azurite["is_a"]) == (
            "material", "Azurite", "extracted", ["copper-ore"],
        )
        assert azurite["description"].startswith("Carbonate mineral. Formula Cu₃(CO₃)₂(OH)₂.")
        assert azurite["references"][0]["citation"].startswith("Calgaro, I.")

    def test_its_hardness_comes_from_wikidata(self, graph):
        assert graph.things["azurite"]["quantities"]["hardness_mohs"] == [3.5, 4]

    def test_it_is_mined_from_its_own_deposit_like_its_template(self, graph):
        route, template = graph.routes["mine-azurite"], graph.routes["mine-malachite"]
        assert route["label"] == "Mining azurite with stone hammers"
        assert route["achieves"] == {"thing": "azurite"}
        assert route["requires"][0] == {"role": "consumed", "thing": "azurite-deposit"}
        assert route["requires"][1:] == template["requires"][1:]
        assert route["references"] == template["references"]
        assert graph.things["azurite-deposit"]["kind"] == "source"

    def test_its_deposits_are_on_the_map(self, built_dir):
        from capabilities.built import load_occurrences

        places = [row for row in load_occurrences(built_dir) if row["source_id"] == "chalcopyrite-deposit"]
        assert places and all(row["matched_on"] == "ore: Chalcopyrite" for row in places)

    def test_a_rejected_mineral_builds_nothing(self, graph):
        assert "pyrite" not in graph.things and "pyrite-deposit" not in graph.things

    def test_a_mineral_may_not_reuse_a_curated_id(self, data_copy, tmp_path):
        crosswalk = data_copy / "data" / "crosswalks" / "ore_minerals.csv"
        crosswalk.write_text(crosswalk.read_text().replace("azurite,Q108212", "hematite,Q108212"), encoding="utf-8")
        with pytest.raises(BuildError, match="ore_minerals_are_new_and_well_formed"):
            build(data_copy, tmp_path / "build")


class TestRoasting:
    def test_copper_sulphides_are_roasted_into_an_ore_that_smelts_to_copper(self, graph):
        assert graph.members("copper-sulphide-ore") == {"bornite", "chalcocite", "chalcopyrite"}
        assert "roasted-copper-ore" in graph.members("copper-ore")

    def test_a_sulphide_deposit_is_enough_for_copper(self, graph):
        # given: stone, timber and fire, and a chalcopyrite deposit, but no oxide copper ore
        selected = Selection.parse(["chalcopyrite-deposit", "fieldstone"])
        # when: exploring
        result = explore(graph, selected)
        # then: chalcopyrite is mined, roasted and smelted to copper
        assert {"chalcopyrite", "roasted-copper-ore", "copper"} <= set(result.reachable)


class TestCurationQueue:
    @pytest.fixture(scope="class")
    def queue(self, built_dir) -> list[dict]:
        return load_queue(built_dir)

    def test_ore_candidates_are_the_unreviewed_minerals_of_copper_iron_and_tin_deposits_most_listed_first(self, queue):
        candidates = [item for item in queue if item["kind"] == "ore_candidate"]
        assert candidates[0]["label"] == "Galena"
        assert [item["priority"] for item in candidates] == sorted((item["priority"] for item in candidates), reverse=True)
        assert all(item["priority"] >= 20 for item in candidates)
        # Reviewed minerals, taken or rejected, and those of curated source kinds, are off the list.
        reviewed = {"azurite", "chalcopyrite", "pyrite", "hematite", "malachite", "cassiterite", "copper"}
        assert not reviewed & {item["subject"] for item in candidates}

    def test_it_lists_sources_with_no_places_and_routes_with_only_unverified_references(self, queue):
        kinds = {item["kind"] for item in queue}
        assert {"source_without_places", "route_unverified"} <= kinds
        assert {item["subject"] for item in queue if item["kind"] == "source_without_places"} == {
            "bog-iron-deposit", "dolerite-outcrop",
        }

    def test_every_extracted_material_has_a_route_and_no_value_disagrees(self, queue):
        kinds = {item["kind"] for item in queue}
        assert not kinds & {"extracted_without_route", "upstream_disagreement", "stale_override"}

    def test_the_queue_command_shows_the_top_of_each_kind(self, repo_root, built_dir, capsys):
        from capabilities.cli import main

        assert main(["--root", str(repo_root), "--build-dir", str(built_dir), "queue", "--limit", "2"]) == 0
        output = capsys.readouterr().out
        assert "ore_candidate (" in output and "  Galena: Listed as an ore mineral on " in output
        assert "--kind ore_candidate --limit 0 for all" in output


class TestProvenanceInTheApp:
    def test_an_upstream_node_says_where_it_came_from(self, graph):
        from capabilities.views import about

        assert about(graph, "azurite")["upstream"] == {
            "dataset": "Wikidata",
            "record": "Q108212",
            "url": "https://www.wikidata.org/wiki/Q108212",
            "crosswalk": "data/crosswalks/ore_minerals.csv",
        }
        assert "upstream" not in about(graph, "malachite")
