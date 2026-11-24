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
        assert graph.things["azurite-deposit"]["kind"] == "source"

    def test_its_route_keeps_the_templates_references_unverified_and_says_whose_they_are(self, graph):
        # given: the iron template cites a checked source (status secondary) about mining hematite, not magnetite
        template, route = graph.routes["mine-hematite"], graph.routes["mine-magnetite"]
        assert template["references"][0]["status"] == "secondary"
        # then: the copy keeps every citation, unverified, and says it was cited for the template
        assert [r["citation"] for r in route["references"]] == [r["citation"] for r in template["references"]]
        assert {r["status"] for r in route["references"]} == {"unverified"}
        assert route["references"][0]["supports"] == (
            "Cited for the route this copies (Mining hematite with stone tools): " + template["references"][0]["supports"]
        )

    def test_its_deposits_are_on_the_map(self, built_dir):
        from capabilities.built import load_occurrences

        places = [row for row in load_occurrences(built_dir) if row["source_id"] == "chalcopyrite-deposit"]
        assert places and all(row["matched_on"] == "ore: Chalcopyrite" for row in places)

    def test_a_rejected_mineral_builds_nothing(self, graph):
        assert "pyrite" not in graph.things and "pyrite-deposit" not in graph.things

    def test_a_crosswalked_item_missing_from_the_wikidata_snapshot_stops_the_build(self, data_copy, tmp_path):
        # given: a row added after the last download, so Wikidata's copy has no name or description for it
        crosswalk = data_copy / "data" / "crosswalks" / "ore_minerals.csv"
        row = 'covellite,Q99999999,Covellite,copper-sulphide-ore,mine-malachite,"A citation.",,"What it supports.",,\n'
        crosswalk.write_text(crosswalk.read_text() + row, encoding="utf-8")
        # then: the build stops rather than build the node without its Wikidata data
        with pytest.raises(BuildError, match="crosswalked_items_are_in_the_wikidata_items_snapshot"):
            build(data_copy, tmp_path / "build")

    @pytest.mark.parametrize("change", [
        pytest.param(("azurite,Q108212", "azurite,108212"), id="a Q id without its Q"),
        pytest.param(("Q50769", "pyrite"), id="a rejected row naming a label, not an item"),
    ])
    def test_every_ore_mineral_names_a_wikidata_item(self, data_copy, tmp_path, change):
        crosswalk = data_copy / "data" / "crosswalks" / "ore_minerals.csv"
        crosswalk.write_text(crosswalk.read_text().replace(*change), encoding="utf-8")
        with pytest.raises(BuildError, match="wikidata_crosswalk_ids_are_items"):
            build(data_copy, tmp_path / "build")

    def test_a_template_must_name_the_material_it_mines(self, data_copy, tmp_path):
        # given: a template whose label doesn't name its material, so the copy would keep it ("Mining malachite…")
        template = data_copy / "data" / "routes" / "mine-malachite.yaml"
        template.write_text(template.read_text().replace("label: Mining malachite with stone hammers",
                                                         "label: Mining copper ore with stone hammers"), encoding="utf-8")
        with pytest.raises(BuildError, match="ore_minerals_are_new_and_well_formed"):
            build(data_copy, tmp_path / "build")

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

        crosswalk = "data/crosswalks/ore_minerals.csv"
        assert about(graph, "azurite")["upstream"] == {
            "dataset": "Wikidata", "record": "Q108212", "url": "https://www.wikidata.org/wiki/Q108212", "crosswalk": crosswalk,
        }
        # A deposit's places come from MRDS, many records, so there is no one record to open.
        assert about(graph, "azurite-deposit")["upstream"] == {
            "dataset": "MRDS", "record": "deposits listing Azurite as an ore mineral", "crosswalk": crosswalk,
        }
        assert "upstream" not in about(graph, "malachite")

    def test_a_copied_route_names_the_route_it_copies(self, graph):
        from capabilities.views import node_source

        assert node_source(graph, "mine-azurite") == {
            "crosswalk": "data/crosswalks/ore_minerals.csv",
            "copied_from": {"id": "mine-malachite", "label": "Mining malachite with stone hammers"},
        }
