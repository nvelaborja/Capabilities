"""Comparing the graph with history (ADR 0053): Seshat's codings, a profile generated for each polity, and the comparison.

The recording is Seshat's codings of the five compared variables for the Middle Kingdom and the Saite Period of Egypt
(conftest), served by a stand-in for its API. With the Cliopatria sample, both polities have areas: the Middle Kingdom's
holds Aswan's granite quarry, worked only by 1086 BCE; the Saite Period's holds it too, and Cyprus's copper mines.
"""

import json
import shutil
from pathlib import Path

import duckdb
import pytest

from capabilities.built import graph_dir, load_profile_occurrences, load_profile_places, load_queue, run_backtest
from capabilities.history import Polity, compare_with_history, load_gaps, load_results, outcome

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def table(build_dir: Path, name: str) -> list[dict]:
    relation = duckdb.read_parquet(str(graph_dir(build_dir) / name))
    return [dict(zip(relation.columns, row)) for row in relation.fetchall() if row[0] is not None]


@pytest.fixture
def compared(upstream_built_dir, tmp_path) -> Path:
    """A copy of the sample build, compared with history: the comparison writes beside the graph."""
    build_dir = tmp_path / "build"
    shutil.copytree(upstream_built_dir, build_dir)
    run_backtest(REPO_ROOT, build_dir)
    return build_dir


def result(build_dir: Path, polity: str, variable: str) -> dict:
    return next(row for row in load_results(graph_dir(build_dir)) if row["seshat_polity"] == polity
                and row["variable"] == variable)


class TestDownload:
    def test_every_coding_of_every_variable_the_crosswalk_names_is_kept(self, tmp_path, seshat_endpoint):
        from capabilities_pipeline.upstream import fetch

        recording = json.loads((FIXTURES / "seshat-sample.json").read_text(encoding="utf-8"))
        snapshot = fetch(seshat_endpoint.dataset, tmp_path, seshat_endpoint.url, root=REPO_ROOT)
        assert snapshot["rows"] == sum(len(codings) for codings in recording.values())
        assert snapshot["variables"] == sorted(recording)
        assert snapshot["license"].startswith("CC BY-SA 4.0")
        rows = duckdb.read_parquet(str(seshat_endpoint.dataset.parquet(tmp_path))).fetchall()
        assert {row[1] for row in rows} == {str(coding["id"]) for codings in recording.values() for coding in codings}

    def test_the_download_follows_the_pages(self, tmp_path, seshat_endpoint):
        from capabilities_pipeline.upstream import fetch

        before = len(seshat_endpoint.requests)
        fetch(seshat_endpoint.dataset, tmp_path, seshat_endpoint.url, root=REPO_ROOT)
        # The stand-in answers one coding a page, so each is a request of its own.
        assert len(seshat_endpoint.requests) - before == fetch(
            seshat_endpoint.dataset, tmp_path / "again", seshat_endpoint.url, root=REPO_ROOT)["rows"]

    def test_a_coding_with_its_value_in_two_fields_is_an_error_not_a_guess(self):
        from capabilities_pipeline.upstream import seshat_row

        coding = json.loads((FIXTURES / "seshat-sample.json").read_text(encoding="utf-8"))["wf/irons"][0]
        with pytest.raises(ValueError, match="format changed"):
            seshat_row("wf/irons", {**coding, "steel": "present"})

    def test_a_coding_of_no_polity_is_kept_with_its_polity_empty(self):
        from capabilities_pipeline.upstream import seshat_row

        coding = json.loads((FIXTURES / "seshat-sample.json").read_text(encoding="utf-8"))["wf/irons"][0]
        row = seshat_row("wf/irons", {**coding, "polity": None})
        assert (row["polity_name"], row["value"]) == ("", coding["iron"])


class TestGeneratedProfiles:
    def test_each_polity_seshat_codes_with_cliopatria_borders_has_a_profile(self, upstream_built_dir):
        areas = {row["id"]: row for row in table(upstream_built_dir, "profile_areas.parquet")}
        # The Middle Kingdom's two Cliopatria rows carry its Seshat id; the Saite Period's are the Twenty-sixth Dynasty's.
        middle = areas["seshat-eg_middle_k"]
        assert (middle["origin"], middle["label"], middle["from_year"], middle["to_year"]) == (
            "seshat", "Egypt - Middle Kingdom", -2016, -1700)
        assert (middle["cliopatria"], middle["cliopatria_rows"]) == ("Middle Kingdom of Egypt", 2)
        assert areas["seshat-eg_saite"]["cliopatria"] == "Twenty-sixth Dynasty of Egypt"
        assert areas["middle-kingdom-egypt"]["origin"] == "curated"

    def test_a_relations_borders_are_not_its_members_area(self, data_copy, tmp_path, pleiades_gz, pleiades_periods_ttl,
                                                          cliopatria_release, seshat_endpoint):
        # given: a relation that carries the Saite Period's Seshat id, as Cliopatria's "(X nominally subject to Y)" rows
        # carry their members', with Grimes Graves (England) inside its borders
        from dataclasses import replace
        import zipfile

        from capabilities_pipeline.build import build
        from capabilities_pipeline.upstream import PLEIADES, PLEIADES_PERIODS, fetch

        collection = json.loads((FIXTURES / "cliopatria-sample.geojson").read_text(encoding="utf-8"))
        relation = json.loads(json.dumps(collection["features"][-1]))
        relation["properties"].update(Name="(Saite Egypt nominally subject to Somewhere)", Type="RELATION")
        relation["geometry"] = {"type": "Polygon", "coordinates": [[[-1, 51], [2, 51], [2, 54], [-1, 54], [-1, 51]]]}
        collection["features"].append(relation)
        directory = tmp_path / "relation"
        (directory / "v1").mkdir(parents=True)
        with zipfile.ZipFile(directory / "v1" / "cliopatria.geojson.zip", "w") as zipped:
            zipped.writestr("cliopatria.geojson", json.dumps(collection))
        (directory / "latest.json").write_text(json.dumps({"tag_name": "v1"}), encoding="utf-8")
        build_dir = tmp_path / "build"
        fetch(PLEIADES, build_dir, pleiades_gz)
        fetch(PLEIADES_PERIODS, build_dir, pleiades_periods_ttl)
        fetch(replace(cliopatria_release.dataset, archive=directory.as_uri() + "/{tag}/cliopatria.geojson.zip"),
              build_dir, (directory / "latest.json").as_uri())
        fetch(seshat_endpoint.dataset, build_dir, seshat_endpoint.url, root=REPO_ROOT)
        build(data_copy, build_dir)
        saite = {row["id"]: row for row in table(build_dir, "profile_areas.parquet")}["seshat-eg_saite"]
        assert (saite["cliopatria"], saite["cliopatria_rows"]) == ("Twenty-sixth Dynasty of Egypt", 3)
        inside = {row["occurrence_id"] for row in table(build_dir, "profile_occurrences.parquet")
                  if row["profile_id"] == "seshat-eg_saite"}
        assert not any("flint" in occurrence for occurrence in inside)

    def test_generated_profiles_stay_out_of_the_apps_profiles(self, upstream_built_dir):
        assert set(load_profile_places(upstream_built_dir)) == {"middle-kingdom-egypt"}
        # Nor does the server hold their occurrences: they would only take memory.
        assert set(load_profile_occurrences(upstream_built_dir)) <= {"middle-kingdom-egypt"}
        assert any(row["profile_id"].startswith("seshat-") for row in table(upstream_built_dir, "profile_occurrences.parquet"))

    def test_a_polity_had_what_seshat_codes_present_in_any_of_its_years(self, upstream_built_dir):
        history = {(row["seshat_polity"], row["variable"]): row for row in table(upstream_built_dir, "history_codings.parquet")}
        saite_iron, saite_steel = history[("eg_saite", "wf/irons")], history[("eg_saite", "wf/steels")]
        assert (saite_iron["history"], saite_steel["history"]) == ("present", "absent")
        assert history[("eg_middle_k", "wf/irons")]["history"] == "absent"
        assert saite_iron["records"] and saite_iron["tags"] == ["TRS"]


class TestComparison:
    def test_a_metal_seshat_records_that_the_areas_sources_dont_reach_names_what_is_missing(self, compared):
        # given: the Middle Kingdom's area, where no copper source is mapped
        copper = result(compared, "eg_middle_k", "wf/coppers")
        assert (copper["history"], copper["graph"], copper["outcome"]) == ("present", "no", "history_yes_graph_no")
        assert copper["cause"] == "absent" and "malachite-deposit" in copper["missing"]

    def test_a_worked_mine_that_doesnt_say_which_ore_is_named(self, compared):
        # given: the Saite Period's area, which holds Cyprus: Agrokipia's copper mine, worked by 550 BCE, is of the
        # copper ore classes; of sources, only Aswan's granite quarry was worked by 525 BCE
        copper = result(compared, "eg_saite", "wf/coppers")
        assert copper["had"] == ["granite-outcrop"] and copper["outcome"] == "history_yes_graph_no"
        assert (copper["cause"], copper["missing"]) == ("ore_unrecorded", ["copper-ore", "copper-sulphide-ore"])

    def test_bronze_names_only_what_is_missing_with_every_place_there(self, compared):
        # given: the Saite Period's area has copper mines (of an ore class) but nothing with tin
        bronze = result(compared, "eg_saite", "wf/bronzes")
        assert bronze["cause"] == "absent" and "copper" not in bronze["missing"] and "Tin" in bronze["reason"]

    def test_neither_recorded_nor_reached_agrees(self, compared):
        assert result(compared, "eg_saite", "wf/steels")["outcome"] == "agree"

    def test_mines_and_quarries_are_compared_with_what_was_worked_in_the_area(self, compared):
        # Saite: Aswan's quarry, worked by 1086 BCE. Middle Kingdom: the same quarry, not known worked by 1700 BCE.
        assert result(compared, "eg_saite", "sc/mines-or-quarries")["outcome"] == "agree"
        middle = result(compared, "eg_middle_k", "sc/mines-or-quarries")
        assert (middle["graph"], middle["outcome"]) == ("maybe", "unknown")

    def test_gaps_group_what_history_shows_and_the_graph_cant_reach(self, compared):
        gaps = {gap["id"]: gap for gap in load_gaps(graph_dir(compared))}
        saite = result(compared, "eg_saite", "wf/bronzes")
        bronze = next(gap for gap in gaps.values() if (gap["thing"], gap["cause"], gap["missing"]) ==
                      ("tin-bronze", "absent", saite["missing"]))
        assert bronze["polities"] == len([row for row in load_results(graph_dir(compared))
                                          if row["thing"] == "tin-bronze" and row["outcome"] == "history_yes_graph_no"
                                          and row["missing"] == saite["missing"]])
        assert "Egypt - Saite Period" in bronze["examples"]

    def test_the_gaps_join_the_queue_while_the_comparison_is_of_the_current_build(self, compared):
        queued = [item for item in load_queue(compared) if item["kind"] == "history_gap"]
        assert {item["subject"] for item in queued} == {gap["id"] for gap in load_gaps(graph_dir(compared))}
        # A build since the comparison makes it stale: its gaps leave the queue until it runs again.
        summary = graph_dir(compared) / "backtest.json"
        summary.write_text(json.dumps({**json.loads(summary.read_text()), "fingerprint": "older"}), encoding="utf-8")
        assert not [item for item in load_queue(compared) if item["kind"] == "history_gap"]


class TestCauses:
    """What the comparison says about a no, on the graph built from the cold backups, with made-up polities."""

    @staticmethod
    def polity(had=(), present=(), classes_worked=(), classes_there=()) -> Polity:
        """A made-up polity: sources had and present, and ore classes with a mine worked by then, or only there."""
        return Polity(id="seshat-test", label="Test", polity="test", years=(-1000, -500), had=frozenset(had),
                      found=frozenset(present) | frozenset(had) | frozenset(classes_worked) | frozenset(classes_there),
                      worked=frozenset(had) | frozenset(classes_worked), present=frozenset(present) | frozenset(had))

    @staticmethod
    def coding(history: str, thing: str = "copper") -> dict:
        return {"profile_id": "seshat-test", "polity_id": 1, "seshat_polity": "test", "variable": "wf/coppers",
                "compares": "thing", "thing": thing, "history": history, "tags": ["TRS"], "disputed": False,
                "records": ["1"]}

    def compare(self, graph, polity: Polity, history: str, thing: str = "copper") -> dict:
        return compare_with_history(graph, {polity.id: polity}, [self.coding(history, thing)])[0]

    def test_a_source_there_but_not_dated_is_a_date_to_find(self, graph):
        row = self.compare(graph, self.polity(present=["malachite-deposit"]), "present")
        assert (row["outcome"], row["cause"], row["missing"]) == ("history_yes_graph_no", "undated", ["malachite-deposit"])

    def test_a_mine_of_an_ore_class_worked_by_then_is_an_ore_to_record(self, graph):
        # given: a Pleiades copper mine worked by then, which doesn't say which ore, so it can't be had
        row = self.compare(graph, self.polity(classes_worked=["copper-ore"]), "present")
        assert (row["cause"], row["missing"]) == ("ore_unrecorded", ["copper-ore"])

    def test_a_mine_of_an_ore_class_there_but_not_dated_is_a_date_to_find(self, graph):
        # given: Serabit el-Khadim in the Middle Kingdom: copper mines, not known to be worked by then
        row = self.compare(graph, self.polity(classes_there=["copper-ore"]), "present")
        assert (row["cause"], row["missing"]) == ("undated", ["copper-ore"])

    def test_nothing_there_is_a_source_absent(self, graph):
        row = self.compare(graph, self.polity(present=["granite-outcrop"]), "present")
        assert row["cause"] == "absent" and "malachite-deposit" in row["missing"]

    def test_with_nothing_there_for_either_metal_bronze_needs_both(self, graph):
        row = self.compare(graph, self.polity(present=["granite-outcrop"]), "present", "tin-bronze")
        assert (row["cause"], row["missing"]) == ("absent", ["copper", "tin-ore"])

    def test_an_absent_cause_names_only_what_no_place_there_gives(self, graph):
        # given: copper mines there, not known to be worked by then, and nothing with tin: the tin is what is absent
        row = self.compare(graph, self.polity(classes_there=["copper-ore"]), "present", "tin-bronze")
        assert row["cause"] == "absent" and "copper" not in row["missing"]

    def test_a_worked_ore_class_and_an_undated_source_together_are_a_date_to_find(self, graph):
        # given: copper from a worked mine that doesn't say which ore, tin only from a place not known worked by then
        row = self.compare(graph, self.polity(present=["tin-gravel"], classes_worked=["copper-ore"]), "present",
                           "tin-bronze")
        assert (row["cause"], row["missing"]) == ("undated", ["tin-gravel"]) and "copper ore" in row["reason"]

    def test_a_source_worked_by_then_reaches_the_metal(self, graph):
        assert self.compare(graph, self.polity(had=["malachite-deposit"]), "present")["outcome"] == "agree"

    def test_reaching_what_seshat_doesnt_record_is_the_weaker_disagreement(self, graph):
        assert self.compare(graph, self.polity(had=["malachite-deposit"]), "absent")["outcome"] == "graph_yes_history_no"

    @pytest.mark.parametrize(("history", "graph", "expected"), [
        ("present", "yes", "agree"), ("absent", "no", "agree"), ("present", "no", "history_yes_graph_no"),
        ("absent", "yes", "graph_yes_history_no"), ("unknown", "yes", "unknown"), ("present", "maybe", "unknown"),
    ])
    def test_outcomes(self, history, graph, expected):
        assert outcome(history, graph) == expected

    def test_nothing_from_the_comparison_is_written_to_the_curated_layer(self, compared):
        # Seshat's data is CC BY-SA 4.0 (ADR 0053): its results live in the build.
        assert all(path.is_relative_to(compared) for path in
                   [graph_dir(compared) / name for name in ("backtest_results.parquet", "graph_gaps.parquet")])
        assert not list((REPO_ROOT / "data").rglob("*backtest*")) and not list((REPO_ROOT / "data").rglob("*seshat_codings*"))
