"""Profiles in space and time (ADR 0052): Cliopatria's borders, a profile's area, and the sources found inside it.

The recording is five real Cliopatria rows (conftest): the Middle Kingdom of Egypt (2000-1601 BCE), whose area holds
Aswan's quarries, and the Twenty-sixth Dynasty (615-531 BCE), whose last row holds Cyprus as well. With the Pleiades
sample, Aswan's granite quarry was worked by 1086 BCE (the end of the New Kingdom) and Agrokipia's copper mine by 550 BCE.
"""

import json
import zipfile
from dataclasses import replace
from pathlib import Path

import duckdb
import pytest

from capabilities.built import (PROFILE_AREAS_FILE, PROFILE_OCCURRENCES_FILE, PROFILE_SOURCES_FILE, graph_dir, load_built,
                                load_occurrences)
from capabilities_pipeline.build import BuildError, build

FIXTURES = Path(__file__).resolve().parent / "fixtures"

SAITE = """id: saite-egypt
kind: profile
label: Saite Egypt
period: 550-531 BCE
place: {{ cliopatria: {place} }}
years: [{first}, {last}]
description: A test profile, the Twenty-sixth Dynasty when it held Cyprus.
includes:
  - {{ id: {include} }}
"""


def write_profile(root: Path, place: str = "Twenty-sixth Dynasty of Egypt", first: int = -550, last: int = -531,
                  include: str = "copper") -> None:
    (root / "data" / "profiles" / "saite-egypt.yaml").write_text(
        SAITE.format(place=place, first=first, last=last, include=include), encoding="utf-8"
    )


@pytest.fixture
def downloads(pleiades_gz, pleiades_periods_ttl, cliopatria_release):
    """Downloads the Pleiades and Cliopatria samples into a build directory; the rest come from the cold backups."""
    from capabilities_pipeline.upstream import PLEIADES, PLEIADES_PERIODS, fetch

    def download(build_dir: Path) -> Path:
        fetch(PLEIADES, build_dir, pleiades_gz)
        fetch(PLEIADES_PERIODS, build_dir, pleiades_periods_ttl)
        fetch(cliopatria_release.dataset, build_dir, cliopatria_release.url)
        return build_dir

    return download


@pytest.fixture
def saite_build(data_copy, tmp_path, downloads) -> Path:
    write_profile(data_copy)
    build_dir = downloads(tmp_path / "build")
    build(data_copy, build_dir)
    return build_dir


def table(build_dir: Path, name: str) -> list[dict]:
    relation = duckdb.read_parquet(str(graph_dir(build_dir) / name))
    return [dict(zip(relation.columns, row)) for row in relation.fetchall() if row[0] is not None]


def points(coordinates: list) -> int:
    """How many positions a GeoJSON polygon or multipolygon has."""
    return 1 if isinstance(coordinates[0], (int, float)) else sum(points(part) for part in coordinates)


def sources_of(build_dir: Path, profile: str) -> dict[str, dict]:
    return {row["source_id"]: row for row in table(build_dir, PROFILE_SOURCES_FILE) if row["profile_id"] == profile}


class TestDownload:
    def test_each_row_is_kept_as_published_with_its_polygons_and_the_release_is_recorded(self, tmp_path, cliopatria_release):
        from capabilities_pipeline.upstream import fetch

        snapshot = fetch(cliopatria_release.dataset, tmp_path, cliopatria_release.url)
        features = json.loads((FIXTURES / "cliopatria-sample.geojson").read_text(encoding="utf-8"))["features"]
        assert (snapshot["rows"], snapshot["release"]) == (len(features), "v0.2.2")
        assert snapshot["license"].startswith("CC BY 4.0")
        with duckdb.connect() as connection:
            connection.load_extension("spatial")
            rows = connection.execute(
                "select Name, FromYear, ToYear, st_npoints(st_geomfromwkb(geometry)) from read_parquet(?)",
                [str(cliopatria_release.dataset.parquet(tmp_path))],
            ).fetchall()
        published = [(f["properties"]["Name"], str(f["properties"]["FromYear"]), str(f["properties"]["ToYear"]),
                      points(f["geometry"]["coordinates"])) for f in features]
        assert sorted(rows) == sorted(published)

    def test_changed_properties_are_an_error_not_a_column_left_out(self, tmp_path, cliopatria_release):
        from capabilities_pipeline.upstream import fetch

        collection = json.loads((FIXTURES / "cliopatria-sample.geojson").read_text(encoding="utf-8"))
        for feature in collection["features"]:
            feature["properties"]["Polity"] = feature["properties"].pop("Name")
        directory = tmp_path / "changed"
        (directory / "v9").mkdir(parents=True)
        with zipfile.ZipFile(directory / "v9" / "cliopatria.geojson.zip", "w") as zipped:
            zipped.writestr("cliopatria.geojson", json.dumps(collection))
        (directory / "latest.json").write_text(json.dumps({"tag_name": "v9"}), encoding="utf-8")
        dataset = replace(cliopatria_release.dataset, archive=directory.as_uri() + "/{tag}/cliopatria.geojson.zip")
        with pytest.raises(ValueError, match="properties changed"):
            fetch(dataset, tmp_path / "build", (directory / "latest.json").as_uri())


class TestAreas:
    def test_a_profiles_area_is_its_entitys_borders_in_the_rows_that_overlap_its_years(self, upstream_built_dir):
        # given: Middle Kingdom Egypt, 2050-1650 BCE, and Cliopatria's two rows for it, 2000-1801 and 1800-1601 BCE
        area = {row["id"]: row for row in table(upstream_built_dir, PROFILE_AREAS_FILE)}["middle-kingdom-egypt"]
        assert (area["cliopatria_rows"], area["cliopatria_from_year"], area["cliopatria_to_year"]) == (2, -2000, -1601)
        assert (area["cliopatria_release"], area["wikidata"]) == ("v0.2.2", "Q191324")
        assert json.loads(area["geojson"])["type"] in ("Polygon", "MultiPolygon")

    def test_rows_outside_the_profiles_years_are_left_out(self, saite_build):
        # given: the Twenty-sixth Dynasty's three rows, of which only 550-531 BCE overlaps the profile
        area = {row["id"]: row for row in table(saite_build, PROFILE_AREAS_FILE)}["saite-egypt"]
        assert (area["cliopatria_rows"], area["cliopatria_from_year"]) == (1, -550)

    @pytest.mark.parametrize(("place", "first", "last"), [
        ("Twenty-Sixth Dynasty of Egypt", -550, -531),
        ("Twenty-sixth Dynasty of Egypt", -1000, -900),
    ], ids=["a misspelt entity", "years when it had no borders"])
    def test_a_place_with_no_area_stops_the_build(self, data_copy, tmp_path, downloads, place, first, last):
        write_profile(data_copy, place, first, last)
        with pytest.raises(BuildError, match="profile_places_have_areas"):
            build(data_copy, downloads(tmp_path / "build"))

    def test_cliopatrias_year_0_is_1_bce(self, data_copy, tmp_path, downloads, cliopatria_release):
        # given: a row that ends in year 0, as Cliopatria writes the last range before AD 1 (-14 to 0, then 1 to 5)
        from capabilities_pipeline.upstream import fetch

        collection = json.loads((FIXTURES / "cliopatria-sample.geojson").read_text(encoding="utf-8"))
        collection["features"][-1]["properties"].update(FromYear=-14, ToYear=0)
        directory = tmp_path / "zero"
        (directory / "v0").mkdir(parents=True)
        with zipfile.ZipFile(directory / "v0" / "cliopatria.geojson.zip", "w") as zipped:
            zipped.writestr("cliopatria.geojson", json.dumps(collection))
        (directory / "latest.json").write_text(json.dumps({"tag_name": "v0"}), encoding="utf-8")
        build_dir = downloads(tmp_path / "build")
        fetch(replace(cliopatria_release.dataset, archive=directory.as_uri() + "/{tag}/cliopatria.geojson.zip"),
              build_dir, (directory / "latest.json").as_uri())
        write_profile(data_copy, first=-14, last=-1)
        build(data_copy, build_dir)
        area = {row["id"]: row for row in table(build_dir, PROFILE_AREAS_FILE)}["saite-egypt"]
        assert (area["cliopatria_from_year"], area["cliopatria_to_year"]) == (-14, -1)


class TestAvailability:
    def test_a_source_worked_inside_the_area_by_the_profiles_last_year_is_had(self, saite_build):
        # given: Aswan's granite quarry, worked by 1086 BCE, inside the Twenty-sixth Dynasty's area in 531 BCE
        granite = sources_of(saite_build, "saite-egypt")["granite-outcrop"]
        assert (granite["availability"], granite["source_kind"]) == ("yes", "source")
        assert granite["worked_by_then"] >= 1
        assert granite["examples"][0]["name"] == "Aswan Quarry Landscape"

    def test_one_there_but_not_known_to_be_worked_by_then_is_only_a_maybe(self, upstream_built_dir):
        # given: the same quarry, in Middle Kingdom Egypt, which ended in 1650 BCE, before 1086
        granite = sources_of(upstream_built_dir, "middle-kingdom-egypt")["granite-outcrop"]
        assert (granite["availability"], granite["worked_by_then"]) == ("maybe", 0)
        assert granite["not_known_worked"] >= 1

    def test_a_source_with_nothing_inside_has_no_row(self, saite_build):
        # given: Grimes Graves' flint, in England
        assert "flint-deposit" not in sources_of(saite_build, "saite-egypt")

    def test_counts_and_marks_agree_with_the_places_inside(self, saite_build):
        inside = [row for row in table(saite_build, PROFILE_OCCURRENCES_FILE) if row["profile_id"] == "saite-egypt"]
        for source_id, source in sources_of(saite_build, "saite-egypt").items():
            mine = [row for row in inside if row["source_id"] == source_id]
            assert source["worked_by_then"] == sum(row["worked_by_then"] for row in mine)
            assert source["not_known_worked"] == sum(not row["worked_by_then"] for row in mine)


class TestSelection:
    def test_the_map_adds_a_source_had_and_never_a_maybe_or_an_ore_class(self, saite_build, data_copy):
        from capabilities.profiles import added_by_map, profile_selection

        graph = load_built(data_copy, saite_build)
        sources = sources_of(saite_build, "saite-egypt")
        # given: Agrokipia's copper mine, worked by 550 BCE, is a place of the copper ore class, not of a source
        assert sources["copper-ore"]["availability"] == "yes" and sources["copper-ore"]["source_kind"] == "category"
        selected = profile_selection(graph, "saite-egypt").things
        assert "granite-outcrop" in selected and "copper" in selected
        assert "copper-ore" not in selected
        assert not {source for source, row in sources.items() if row["availability"] == "maybe"} & selected
        assert added_by_map(graph, "saite-egypt") == sorted(
            source for source, row in sources.items() if row["availability"] == "yes" and row["source_kind"] == "source")

    def test_a_listed_source_is_had_wherever_the_map_puts_it(self, upstream_built_dir):
        from capabilities.profiles import profile_selection, sources_from_map

        graph = load_built(Path(__file__).resolve().parents[2], upstream_built_dir)
        # given: Middle Kingdom Egypt lists granite outcrops, which the map makes only a maybe
        assert "granite-outcrop" not in sources_from_map(graph, "middle-kingdom-egypt")
        assert "granite-outcrop" in profile_selection(graph, "middle-kingdom-egypt").things


class TestQueue:
    def test_a_place_of_a_source_the_profile_only_maybe_had_and_doesnt_list_is_queued_for_a_date(
        self, data_copy, tmp_path, downloads,
    ):
        # given: a profile in Middle Kingdom Egypt's place and years that lists only copper, so Aswan's granite quarry,
        # worked by 1086 BCE, is a maybe a date would change
        write_profile(data_copy, "Middle Kingdom of Egypt", -2050, -1650)
        build_dir = downloads(tmp_path / "build")
        build(data_copy, build_dir)
        queued = date_unknown(build_dir)
        aswan = next(row for row in load_occurrences(build_dir) if row["name"] == "Aswan Quarry Landscape")
        item = queued[f"pleiades:{aswan['record_id']}"]
        assert "Saite Egypt" in item["detail"] and "1086 BC" in item["detail"]
        # then: not for Middle Kingdom Egypt, which lists granite outcrops and so has them anyway
        assert "Middle Kingdom Egypt" not in item["detail"]
        assert all(set(item["evidence"]["sources"]) <= source_kinds(data_copy, build_dir) for item in queued.values())

    def test_a_place_of_a_source_the_profile_lists_is_not(self, upstream_built_dir):
        aswan = next(row for row in load_occurrences(upstream_built_dir) if row["name"] == "Aswan Quarry Landscape")
        assert f"pleiades:{aswan['record_id']}" not in date_unknown(upstream_built_dir)

    def test_a_place_of_a_source_already_had_is_not(self, saite_build):
        # given: Aswan's granite quarry, which makes granite outcrops had in Saite Egypt
        assert sources_of(saite_build, "saite-egypt")["granite-outcrop"]["availability"] == "yes"
        aswan = next(row for row in load_occurrences(saite_build) if row["name"] == "Aswan Quarry Landscape")
        assert f"pleiades:{aswan['record_id']}" not in date_unknown(saite_build)

    def test_a_place_of_an_ore_class_is_not(self, saite_build, data_copy):
        # An ore class is never added to a selection, so a date for its mine changes no answer.
        assert all(set(item["evidence"]["sources"]) <= source_kinds(data_copy, saite_build)
                   for item in date_unknown(saite_build).values())


def date_unknown(build_dir: Path) -> dict[str, dict]:
    """The queue's undated places, by subject, with their evidence."""
    items = [row for row in table(build_dir, "curation_queue.parquet") if row["kind"] == "date_unknown"]
    return {row["subject"]: {**row, "evidence": json.loads(row["evidence"])} for row in items}


def source_kinds(root: Path, build_dir: Path) -> set[str]:
    """The ids of every thing of kind source, not class, in the built graph."""
    graph = load_built(root, build_dir)
    return {thing for thing, document in graph.things.items() if document["kind"] == "source"}
