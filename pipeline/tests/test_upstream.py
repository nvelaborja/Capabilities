import json
import shutil
from pathlib import Path

import duckdb
import pytest

from capabilities.built import MANIFEST_FILE, OCCURRENCES_FILE, graph_dir, is_current
from capabilities_pipeline.build import BuildError, build
from capabilities_pipeline.upstream import MRDS, fetch

# Hopong (Burma), a hematite deposit in the sample; the tests remove its coordinates to check that a deposit that can't
# be placed is left out.
UNPLACED = "10003682"


def occurrences(build_dir: Path, dataset: str = "mrds") -> list[dict]:
    """The occurrences from one dataset: MRDS's, unless another is named (Pleiades' are tested in test_pleiades.py)."""
    relation = duckdb.sql(
        "select * exclude (geometry) from read_parquet(?) where id is not null and dataset = ? order by id",
        params=[str(graph_dir(build_dir) / OCCURRENCES_FILE), dataset],
    )
    return [dict(zip(relation.columns, row)) for row in relation.fetchall()]


@pytest.fixture(scope="module")
def mrds_build(repo_root, tmp_path_factory, mrds_zip, sample_rows):
    """The repository's graph built with a snapshot of the sample, in which one hematite deposit has no coordinates."""
    rows = sample_rows()
    for row in rows:
        if row["dep_id"] == UNPLACED:
            row["latitude"] = row["longitude"] = ""
    build_dir = tmp_path_factory.mktemp("build")
    snapshot = fetch(MRDS, build_dir, mrds_zip(tmp_path_factory.mktemp("download"), rows))
    build(repo_root, build_dir)
    return build_dir, snapshot


class TestSnapshot:
    def test_a_snapshot_records_where_and_when_it_was_retrieved_its_hash_and_its_license(self, tmp_path, mrds_zip):
        url = mrds_zip(tmp_path / "download")
        snapshot = fetch(MRDS, tmp_path / "build", url)
        assert snapshot["url"] == url
        assert snapshot["rows"] == 14
        assert snapshot["license"].startswith("US public domain")
        assert len(snapshot["sha256"]) == 64
        assert snapshot["retrieved_at"].endswith("Z")
        on_disk = json.loads((MRDS.directory(tmp_path / "build") / "snapshot.json").read_text())
        assert on_disk == snapshot

    def test_every_published_column_is_kept_as_text_exactly_as_published(self, tmp_path, mrds_zip):
        fetch(MRDS, tmp_path / "build", mrds_zip(tmp_path / "download"))
        relation = duckdb.sql("select * from read_parquet(?)", params=[str(MRDS.parquet(tmp_path / "build"))])
        assert tuple(relation.columns) == MRDS.columns
        assert set(relation.types) == {"VARCHAR"}
        # A leading zero or a trailing ".0" would show that a value had been read as a number.
        assert ("10008106", "39.24", "1860") in relation.select("dep_id, latitude, yr_fst_prd").fetchall()

    def test_a_download_whose_columns_changed_fails_and_leaves_the_last_snapshot_in_place(self, tmp_path, mrds_zip):
        build_dir = tmp_path / "build"
        good = fetch(MRDS, build_dir, mrds_zip(tmp_path / "good"))
        renamed = ["ore_minerals" if column == "ore" else column for column in MRDS.columns]
        with pytest.raises(ValueError, match="columns changed"):
            fetch(MRDS, build_dir, mrds_zip(tmp_path / "renamed", columns=renamed))
        assert json.loads((MRDS.directory(build_dir) / "snapshot.json").read_text()) == good

    def test_a_new_snapshot_makes_the_built_graph_stale(self, repo_root, tmp_path, mrds_zip, sample_rows):
        build_dir = tmp_path / "build"
        fetch(MRDS, build_dir, mrds_zip(tmp_path / "first"))
        build(repo_root, build_dir)
        assert is_current(repo_root, build_dir)
        fetch(MRDS, build_dir, mrds_zip(tmp_path / "second", rows=sample_rows()[:5]))
        assert not is_current(repo_root, build_dir)


# The source kinds of the upstream ore minerals (ADR 0045), whose places come from the ore crosswalk, not mrds_sources.
ORE_SOURCES = {
    f"{mineral}-deposit"
    for mineral in ("azurite", "cuprite", "tenorite", "chalcocite", "bornite", "chalcopyrite", "magnetite", "goethite", "siderite")
}


class TestOccurrences:
    def test_each_deposit_is_an_occurrence_of_every_source_kind_the_crosswalk_matches(self, mrds_build):
        found = {(row["source_id"], row["record_id"]) for row in occurrences(mrds_build[0]) if row["source_id"] not in ORE_SOURCES}
        assert found == {
            ("hematite-deposit", "10001442"),  # Copper Wonder lists hematite and malachite, so it is both
            ("malachite-deposit", "10001442"),
            ("tin-gravel", "10001702"),  # a cassiterite placer
            ("limestone-outcrop", "10003991"),  # commodity "Limestone, General"
            ("granite-outcrop", "10004806"),
            ("hematite-deposit", "10008106"),
            ("malachite-deposit", "10008132"),
            ("diamond-gravel", "10021397"),  # a diamond placer
            ("malachite-deposit", "10025716"),
            ("native-copper-deposit", "10080379"),  # ore mineral "Copper"
        }

    def test_an_upstream_ore_minerals_places_are_the_deposits_listing_it_as_an_ore(self, mrds_build):
        found = {(row["source_id"], row["record_id"]) for row in occurrences(mrds_build[0]) if row["source_id"] in ORE_SOURCES}
        assert found == {
            ("azurite-deposit", "10001442"),  # Copper Wonder: azurite and chalcopyrite among its ores
            ("chalcopyrite-deposit", "10001442"),
            ("chalcopyrite-deposit", "10008106"),  # Leadville District: chalcopyrite, magnetite and chalcocite
            ("magnetite-deposit", "10008106"),
            ("chalcocite-deposit", "10008106"),
            ("chalcopyrite-deposit", "10025716"),  # McGraw Mine
        }
        # Hopong lists magnetite too, but in this build it has no coordinates, so it can't be placed.
        assert ("magnetite-deposit", UNPLACED) not in found

    @pytest.mark.parametrize(
        ("record_id", "why"),
        [
            ("10004271", "cassiterite in a vein is not tin gravel"),
            ("10000265", "diamond with no deposit type is not known to be a placer"),
            (UNPLACED, "a deposit without coordinates can't be placed"),
            ("10000034", "gold matches no source kind"),
        ],
    )
    def test_deposits_the_crosswalk_does_not_match_are_left_out(self, mrds_build, record_id, why):
        assert record_id not in {row["record_id"] for row in occurrences(mrds_build[0])}, why

    @pytest.mark.parametrize(
        ("record_id", "worked_by_year", "state"),
        [
            ("10008106", 1860, "worked"),  # first production in 1860
            ("10008132", 1880, "worked"),  # production began before 1880, so it was worked by then
            ("10025716", None, "present"),  # production began after 1880: no year by which it was worked
            ("10001442", None, "present"),  # a prospect with no production year
        ],
    )
    def test_a_deposit_is_worked_only_with_a_year_by_which_it_was_worked(
        self, mrds_build, record_id, worked_by_year, state
    ):
        row = next(row for row in occurrences(mrds_build[0]) if row["record_id"] == record_id)
        assert (row["worked_by_year"], row["state"]) == (worked_by_year, state)

    def test_occurrences_are_geoparquet_points_at_the_deposits_coordinates(self, mrds_build):
        path = str(graph_dir(mrds_build[0]) / OCCURRENCES_FILE)
        keys = {key.decode() for (key,) in duckdb.sql("select key from parquet_kv_metadata(?)", params=[path]).fetchall()}
        assert "geo" in keys
        with duckdb.connect() as connection:
            connection.execute("load spatial")
            point = connection.execute(
                "select distinct st_astext(geometry::geometry) from read_parquet(?) where record_id = '10008106'", [path]
            ).fetchall()
        assert point == [("POINT (-106.26 39.24)",)]

    def test_every_occurrence_names_its_upstream_record_and_snapshot(self, mrds_build):
        build_dir, snapshot = mrds_build
        row = next(
            row for row in occurrences(build_dir) if (row["source_id"], row["record_id"]) == ("hematite-deposit", "10008106")
        )
        assert json.loads(row["provenance"]) == {
            "layer": "upstream",
            "dataset": "mrds",
            "record": "10008106",
            "url": "https://mrdata.usgs.gov/mrds/show-mrds.php?dep_id=10008106",
            "retrieved_at": snapshot["retrieved_at"],
        }
        assert row["matched_on"] == "ore: Hematite"

    def test_the_manifest_records_the_snapshot_and_the_number_of_occurrences(self, mrds_build):
        build_dir, snapshot = mrds_build
        manifest = json.loads((graph_dir(build_dir) / MANIFEST_FILE).read_text())
        # 10 of curated source kinds and 6 of upstream ore minerals from the MRDS sample, and Pleiades' from its backup.
        assert manifest["tables"][OCCURRENCES_FILE] == 16 + len(occurrences(build_dir, "pleiades"))
        # The sample was just downloaded, so it is newer than the cold backup and is used; Wikidata comes from its backup.
        assert manifest["upstream"]["mrds_deposits"] == {
            **{key: snapshot[key] for key in ("url", "retrieved_at", "sha256", "rows", "license")}, "copy": "download"
        }
        assert manifest["upstream"]["wikidata_quantities"]["copy"] == "backup"


REPO_SNAPSHOTS = Path(__file__).resolve().parents[2] / "snapshots"


class TestEveryDatasetIsRequired:
    def test_with_nothing_downloaded_the_cold_backups_are_used(self, built_dir):
        # built_dir (conftest) never downloads anything, like CI and a fresh clone.
        manifest = json.loads((graph_dir(built_dir) / MANIFEST_FILE).read_text())
        assert {name: snapshot["copy"] for name, snapshot in manifest["upstream"].items()} == {
            "mrds_deposits": "backup", "pleiades_places": "backup", "wikidata_items": "backup",
            "wikidata_quantities": "backup",
        }
        assert manifest["tables"][OCCURRENCES_FILE] > 0

    def test_a_build_with_no_copy_of_a_dataset_stops_and_says_how_to_get_one(self, data_copy, tmp_path):
        from capabilities_pipeline.upstream import MissingSnapshot

        # given: no cold backup of MRDS, and nothing downloaded
        (data_copy / "snapshots").unlink()
        shutil.copytree(REPO_SNAPSHOTS, data_copy / "snapshots", ignore=shutil.ignore_patterns("mrds_deposits"))
        # when, then: the build stops before anything is built
        with pytest.raises(MissingSnapshot, match="No copy of mrds_deposits.*upstream/mrds_deposits"):
            build(data_copy, tmp_path / "build")
        assert not (graph_dir(tmp_path / "build") / MANIFEST_FILE).exists()

    def test_backing_up_makes_a_newer_download_the_cold_backup(self, data_copy, tmp_path, mrds_zip):
        from capabilities_pipeline.upstream import back_up, backup_directory

        # given: a fresh download, newer than the backup
        root = data_copy
        (root / "snapshots").unlink()
        shutil.copytree(REPO_SNAPSHOTS, root / "snapshots", ignore=shutil.ignore_patterns("*.parquet"))
        build_dir = tmp_path / "build"
        snapshot = fetch(MRDS, build_dir, mrds_zip(tmp_path / "download"))
        # when: backing up, twice
        first, second = back_up(MRDS, root, build_dir), back_up(MRDS, root, build_dir)
        # then: the backup is the download, value for value; the second time there was nothing newer
        assert first == snapshot and second is None
        backup = backup_directory(MRDS, root) / "mrds_deposits.parquet"
        difference = duckdb.sql(
            "select count(*) from (select * from read_parquet(?) except all select * from read_parquet(?))",
            params=[str(MRDS.parquet(build_dir)), str(backup)],
        ).fetchall()[0][0]
        assert difference == 0

    def test_offline_the_download_falls_back_to_the_cold_backup(self, repo_root, tmp_path):
        from capabilities_pipeline.upstream import fetch_or_fall_back

        # Port 9 refuses connections, as a server that is down or a network that is off would.
        snapshot, error = fetch_or_fall_back(MRDS, repo_root, tmp_path / "build", "http://127.0.0.1:9/mrds-csv.zip")
        assert snapshot["copy"] == "backup" and error


class TestCrosswalk:
    def test_a_crosswalk_row_that_names_something_other_than_a_source_fails_the_build(self, data_copy, tmp_path):
        crosswalk = data_copy / "data" / "crosswalks" / "mrds_sources.csv"
        crosswalk.write_text(crosswalk.read_text() + "hematite,ore,Hematite,,The material, not its deposit.\n")
        with pytest.raises(BuildError, match="crosswalk_maps_to_sources"):
            build(data_copy, tmp_path / "build")

    def test_a_crosswalk_row_that_names_no_node_fails_the_build(self, data_copy, tmp_path):
        crosswalk = data_copy / "data" / "crosswalks" / "mrds_sources.csv"
        crosswalk.write_text(crosswalk.read_text() + "galena-deposit,ore,Galena,,Not in the graph.\n")
        with pytest.raises(BuildError, match="relationships"):
            build(data_copy, tmp_path / "build")


class TestSuppressions:
    def test_a_suppressed_deposit_is_not_an_occurrence(self, data_copy, tmp_path, mrds_zip):
        # given: the Leadville District deposit (10008106) is suppressed as not belonging
        suppressions = data_copy / "data" / "suppressions" / "suppressed_records.csv"
        suppressions.write_text(suppressions.read_text() + 'mrds,10008106,"Test: a duplicate record."\n', encoding="utf-8")
        build_dir = tmp_path / "build"
        fetch(MRDS, build_dir, mrds_zip(tmp_path / "download"))
        # when: building
        build(data_copy, build_dir)
        # then: it is on no map, and the other deposits still are
        records = {row["record_id"] for row in occurrences(build_dir)}
        assert "10008106" not in records
        assert "10001442" in records
