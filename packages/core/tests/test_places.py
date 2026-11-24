import pytest

from capabilities.places import NotPlaceable, Places, places_view


def occurrence(source_id: str, record_id: str, state: str = "present", worked_by_year: int | None = None) -> dict:
    return {
        "id": f"{source_id}/mrds/{record_id}", "source_id": source_id, "dataset": "mrds", "record_id": record_id,
        "name": f"Deposit {record_id}", "longitude": -106.26, "latitude": 39.24, "country": "United States",
        "admin_area": "Colorado", "development_status": "Past Producer", "deposit_type": None,
        "worked_by_year": worked_by_year, "state": state, "attested_from": None, "attested_to": None, "periods": None,
        "approximate": None, "matched_on": "ore: Hematite",
        "url": f"https://mrdata.usgs.gov/mrds/show-mrds.php?dep_id={record_id}",
    }


SNAPSHOTS = {"mrds_deposits": {"url": "https://mrdata.usgs.gov/mrds/mrds-csv.zip", "retrieved_at": "2026-11-22T21:58:22Z",
                               "license": "US public domain (a work of the U.S. Geological Survey)"}}


@pytest.fixture
def places() -> Places:
    return Places.from_rows(
        [
            occurrence("hematite-deposit", "1", "worked", 1860),
            occurrence("hematite-deposit", "2"),
            occurrence("malachite-deposit", "3"),
        ],
        SNAPSHOTS,
    )


class TestWhereAThingIsFound:
    def test_a_material_is_found_wherever_a_source_it_is_extracted_from_is_found(self, graph, places):
        view = places_view(graph, places, "hematite")
        assert [source["id"] for source in view["sources"]] == ["hematite-deposit"]
        assert [f["properties"]["record_id"] for f in view["features"]["features"]] == ["1", "2"]

    def test_a_source_is_found_at_its_own_places(self, graph, places):
        view = places_view(graph, places, "malachite-deposit")
        assert [f["properties"]["record_id"] for f in view["features"]["features"]] == ["3"]

    def test_each_source_says_how_many_places_are_known_and_how_many_were_worked(self, graph, places):
        (summary,) = places_view(graph, places, "hematite")["sources"]
        assert (summary["label"], summary["places"], summary["worked"]) == ("Hematite deposit", 2, 1)

    def test_a_source_with_no_mapped_places_still_says_where_it_is_known_to_be(self, graph, places):
        (summary,) = places_view(graph, places, "limonite")["sources"]
        assert summary["id"] == "bog-iron-deposit"
        assert summary["places"] == 0
        assert summary["regions"]  # the curated regions, shown instead of a map

    def test_a_source_found_almost_everywhere_says_so(self, graph, places):
        (summary,) = places_view(graph, places, "timber")["sources"]
        assert (summary["id"], summary["availability"]) == ("standing-trees", "ubiquitous")

    def test_a_produced_material_has_no_sources(self, graph, places):
        view = places_view(graph, places, "steel")
        assert (view["origin"], view["sources"], view["features"]["features"]) == ("produced", [], [])

    def test_only_materials_and_sources_have_places(self, graph, places):
        with pytest.raises(NotPlaceable):
            places_view(graph, places, "copper-saw")

    def test_points_are_longitude_then_latitude_with_what_the_popup_needs(self, graph, places):
        (first, _) = places_view(graph, places, "hematite")["features"]["features"]
        assert first["geometry"] == {"type": "Point", "coordinates": [-106.26, 39.24]}
        assert first["properties"]["state"] == "worked"
        assert first["properties"]["worked_by_year"] == 1860
        assert first["properties"]["url"].endswith("dep_id=1")
        assert first["properties"]["dataset"] == "mrds"  # names the dataset in the popup's link

    def test_the_datasets_say_where_the_places_came_from_and_when(self, graph, places):
        assert places_view(graph, places, "hematite")["datasets"] == [{
            "id": "mrds",
            "label": "USGS Mineral Resources Data System (MRDS)",
            "short": "MRDS",
            "home": "https://mrdata.usgs.gov/mrds/",
            "note": "Modern records, most of them in the United States; a working year is the year production first began.",
            "retrieved_at": "2026-11-22T21:58:22Z",
            "license": "US public domain (a work of the U.S. Geological Survey)",
        }]

    def test_with_no_snapshot_there_are_no_places_or_datasets(self, graph):
        view = places_view(graph, Places(), "hematite")
        assert (view["sources"][0]["places"], view["datasets"]) == (0, [])
