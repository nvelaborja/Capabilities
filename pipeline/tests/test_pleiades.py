"""Pleiades' ancient mines and quarries as occurrences (ADR 0046).

`upstream_built_dir` (conftest) is the repository's graph built from samples of every dataset, Pleiades' being thirteen
real places that cover each case; `built_dir` and `graph` are built from the cold backups: every Pleiades place.
"""

import csv
import gzip
from pathlib import Path

import duckdb
import pytest

from capabilities.built import load_occurrences, load_queue
from capabilities_pipeline.build import BuildError, build

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[2]


def occurrences_of(build_dir, name: str) -> dict[str, dict]:
    """The Pleiades place's occurrences, by the source or class they belong to."""
    return {row["source_id"]: row for row in load_occurrences(build_dir) if row["dataset"] == "pleiades" and row["name"] == name}


def period_table(build_dir) -> list[dict]:
    """The periods snapshot as downloaded: every column as text, empty years as nulls."""
    from capabilities_pipeline.upstream import PLEIADES_PERIODS

    relation = duckdb.read_parquet(str(PLEIADES_PERIODS.parquet(build_dir)))
    return [dict(zip(relation.columns, row)) for row in relation.fetchall()]


def build_with_periods(tmp_path, periods: dict[str, str]):
    """The repository's graph, with the Pleiades sample downloaded after its places' periods are changed (by record id)
    and the periods sample; the other datasets from their cold backups."""
    from capabilities_pipeline.upstream import PLEIADES, PLEIADES_PERIODS, fetch

    with (FIXTURES / "pleiades-sample.csv").open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        rows, columns = list(reader), reader.fieldnames
    for row in rows:
        row["timePeriodsKeys"] = periods.get(row["id"], row["timePeriodsKeys"])
    sample = tmp_path / "pleiades.csv"
    with sample.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    archive = tmp_path / "pleiades.csv.gz"
    archive.write_bytes(gzip.compress(sample.read_bytes()))
    build_dir = tmp_path / "build"
    fetch(PLEIADES, build_dir, archive.as_uri())
    fetch(PLEIADES_PERIODS, build_dir, (FIXTURES / "pleiades-periods-sample.ttl").as_uri())
    build(REPO_ROOT, build_dir)
    return build_dir


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
        assert agrokipia["state"] == "worked"
        assert (agrokipia["attested_from"], agrokipia["attested_to"]) == (-750, 300)
        assert list(agrokipia["periods"]) == ["archaic", "classical", "hellenistic-republican", "roman"]
        assert agrokipia["url"] == "https://pleiades.stoa.org/places/707452"

    def test_a_rough_location_is_marked_approximate_and_mrds_doesnt_say(self, upstream_built_dir):
        assert occurrences_of(upstream_built_dir, "Temesa Copper Mines")["copper-ore"]["approximate"] is True
        assert occurrences_of(upstream_built_dir, "Agrokipia")["copper-ore"]["approximate"] is False
        assert {row["approximate"] for row in load_occurrences(upstream_built_dir) if row["dataset"] == "mrds"} == {None}

    def test_a_place_attested_only_in_modern_times_stays_since_the_material_was_there(self, tmp_path):
        # given: a mine attested in the twenty-first century only
        build_dir = build_with_periods(tmp_path, {"707452": "twenty-first-ce"})
        agrokipia = occurrences_of(build_dir, "Agrokipia")["copper-ore"]
        assert agrokipia["state"] == "worked"


def period_turtle(key: str, label: str | None = None, note: str | None = None) -> str:
    """One period as Pleiades writes it, with the label and scope note given as Turtle strings."""
    lines = [f"<https://pleiades.stoa.org/vocabularies/{key}> a <http://www.w3.org/2004/02/skos/core#Concept>"]
    lines += [f"    skos:prefLabel {label}@en"] if label is not None else []
    lines += [f"    skos:scopeNote {note}@en"] if note is not None else []
    return ";\n".join(lines) + " .\n\n"


class TestPeriods:
    def test_each_period_is_kept_with_the_years_its_note_gives(self, tmp_path, pleiades_periods_ttl):
        from capabilities_pipeline.upstream import PLEIADES_PERIODS, fetch

        snapshot = fetch(PLEIADES_PERIODS, tmp_path, pleiades_periods_ttl)
        periods = {row["key"]: row for row in period_table(tmp_path)}
        assert snapshot["rows"] == len(periods) == 26
        assert snapshot["license"].startswith("CC BY 3.0")
        roman = periods["roman"]
        assert (roman["label"], roman["from_year"], roman["to_year"]) == ("Roman, early Empire (30 BC-AD 300)", "-30", "300")
        # A note that is missing its last bracket: "[[1, 1000]"
        assert (periods["1st-millennium-ce"]["from_year"], periods["1st-millennium-ce"]["to_year"]) == ("1", "1000")

    def test_a_period_whose_note_gives_no_years_has_none_and_the_snapshot_lists_it(self, tmp_path, pleiades_periods_ttl):
        from capabilities_pipeline.upstream import PLEIADES_PERIODS, fetch

        # given: "fifth century before the common era", with no note; its years are not worked out from its name
        snapshot = fetch(PLEIADES_PERIODS, tmp_path, pleiades_periods_ttl)
        periods = {row["key"]: row for row in period_table(tmp_path)}
        assert (periods["fifth-bce"]["from_year"], periods["fifth-bce"]["to_year"]) == (None, None)
        assert "fifth-bce" in snapshot["undated"] and "roman" not in snapshot["undated"]
        assert snapshot["undated"] == sorted(key for key, row in periods.items() if row["from_year"] is None)

    @pytest.mark.parametrize("turtle", [
        "",
        period_turtle("roman", note='"[[-30, 300]]"'),
        period_turtle("roman", label='""', note='"[[-30, 300]]"'),
        period_turtle("roman", label='"Roman"', note='"""Roman.\n[[-30, 300]]"""'),
        period_turtle("archaic", label='"Archaic"', note='"[[-750, -550]]"')
        + 'pv:roman a skos:Concept;\n    skos:prefLabel "Roman"@en .\n',
    ], ids=["no periods", "a period without a label", "an empty label", "a note in triple quotes",
            "a period written another way"])
    def test_a_changed_format_is_an_error_not_a_period_left_out(self, turtle):
        from capabilities_pipeline.upstream import period_rows

        with pytest.raises(ValueError, match="format changed"):
            period_rows(turtle)

    @pytest.mark.parametrize(("years", "error"), [
        ("[[300, -30]]", "runs backwards"),
        ("[[0, 100]]", "year 0"),
    ], ids=["backwards", "year zero"])
    def test_years_that_are_not_signed_years_running_forward_fail_the_download(self, years, error):
        from capabilities_pipeline.upstream import period_rows

        # given: a note whose years no period could have; the download fails, so the copy the build has stays newest
        with pytest.raises(ValueError, match=error):
            period_rows(period_turtle("roman", label='"Roman"', note=f'"{years}"'))

    def test_the_vocabulary_itself_is_not_a_period(self):
        from capabilities_pipeline.upstream import period_rows

        turtle = period_turtle("roman", label='"Roman"', note='"[[-30, 300]]"') + (
            "<https://pleiades.stoa.org/vocabularies/> a <http://www.w3.org/2004/02/skos/core#ConceptScheme>;\n"
            '    dcterms:title "Time Periods" .\n'
        )
        assert [(row["key"], row["scope_note"]) for row in period_rows(turtle)] == [("roman", "[[-30, 300]]")]


class TestWorkedBy:
    def test_a_place_was_worked_by_the_end_of_its_earliest_period(self, upstream_built_dir):
        # given: Agrokipia, attested in the Archaic (750-550 BCE), Classical, Hellenistic and Roman periods
        agrokipia = occurrences_of(upstream_built_dir, "Agrokipia")["copper-ore"]
        assert (agrokipia["worked_by_year"], agrokipia["worked_by_basis"]) == (-550, "period")
        assert agrokipia["worked_by_note"].startswith("Archaic")
        assert occurrences_of(upstream_built_dir, "Grimes Graves")["flint-deposit"]["worked_by_year"] == -2500

    def test_periods_without_years_are_passed_over(self, upstream_built_dir):
        # given: As Muradellas, attested in the Roman period and the twelfth and thirteenth centuries, which have no years
        assert occurrences_of(upstream_built_dir, "As Muradellas Mine")["tin-ore"]["worked_by_year"] == 300

    def test_a_place_with_only_undated_periods_keeps_no_year_and_is_still_worked(self, tmp_path):
        agrokipia = occurrences_of(build_with_periods(tmp_path, {"707452": "fifth-bce"}), "Agrokipia")["copper-ore"]
        assert (agrokipia["state"], agrokipia["worked_by_year"], agrokipia["worked_by_basis"]) == ("worked", None, None)

    def test_a_period_still_running_ends_when_the_snapshot_was_taken(self, tmp_path):
        # given: a mine attested only in the Modern period, which Pleiades runs to 2100
        build_dir = build_with_periods(tmp_path, {"707452": "modern"})
        from capabilities_pipeline.upstream import PLEIADES, snapshot_of

        retrieved = snapshot_of(PLEIADES, build_dir)["retrieved_at"]
        agrokipia = occurrences_of(build_dir, "Agrokipia")["copper-ore"]
        assert agrokipia["worked_by_year"] == int(retrieved[:4])
        assert agrokipia["worked_by_note"].startswith("Modern")
        # then: the period's own end is kept, so the map doesn't say it had ended by then
        assert agrokipia["worked_by_period_end"] == 2100

    def test_a_period_that_had_ended_is_its_own_end(self, upstream_built_dir):
        agrokipia = occurrences_of(upstream_built_dir, "Agrokipia")["copper-ore"]
        assert agrokipia["worked_by_period_end"] == agrokipia["worked_by_year"] == -550
        assert agrokipia["upstream_worked_by_note"] is None


class TestCuratedDates:
    def test_a_curated_date_wins_over_the_periods_and_keeps_what_they_said(self, data_copy, tmp_path, write_date):
        write_date(data_copy)
        build(data_copy, tmp_path / "build")
        agrokipia = occurrences_of(tmp_path / "build", "Agrokipia")["copper-ore"]
        assert (agrokipia["worked_by_year"], agrokipia["worked_by_basis"]) == (-1200, "curated")
        assert (agrokipia["worked_by_date"], agrokipia["upstream_worked_by_year"]) == ("agrokipia-worked", -550)
        assert agrokipia["upstream_worked_by_note"].startswith("Archaic")
        assert agrokipia["worked_by_note"].startswith("Test only.")
        assert agrokipia["worked_by_references"][0]["citation"].startswith("Test, A. (2026)")

    def test_a_curated_date_makes_a_deposit_with_no_known_date_worked(self, data_copy, tmp_path, built_dir, write_date):
        # given: any MRDS deposit the dataset gives no working date for
        record = next(row["record_id"] for row in load_occurrences(built_dir)
                      if row["dataset"] == "mrds" and row["state"] == "present")
        write_date(data_copy, id="deposit-worked", dataset="mrds", record=record, worked_by=1850)
        build(data_copy, tmp_path / "build")
        dated = [row for row in load_occurrences(tmp_path / "build") if row["record_id"] == record]
        assert dated and all((row["state"], row["worked_by_year"]) == ("worked", 1850) for row in dated)
        assert {row["upstream_worked_by_year"] for row in dated} == {None}

    def test_two_dates_of_one_record_fail_the_build(self, data_copy, tmp_path, write_date):
        write_date(data_copy)
        write_date(data_copy, id="agrokipia-worked-again", worked_by=-1100)
        with pytest.raises(BuildError, match="dates_are_one_per_record"):
            build(data_copy, tmp_path / "build")


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
