import pytest
from fastapi.testclient import TestClient

from capabilities_api.server import create_app


@pytest.fixture(scope="module")
def client(repo_root, built_dir, tmp_path_factory) -> TestClient:
    # Ignore any local web build so results don't depend on whether `npm run build` has been run.
    return TestClient(create_app(repo_root, web_dist=tmp_path_factory.mktemp("no-web-build"), build_dir=built_dir))


class TestServer:
    def test_health(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_nodes_can_be_filtered_by_kind(self, client):
        kinds = {node["kind"] for node in client.get("/api/nodes", params={"kind": "verb"}).json()}
        assert kinds == {"verb"}

    def test_node_detail_lists_routes(self, client):
        body = client.get("/api/nodes/steel").json()
        assert set(body["made_by"]) == {"steel-by-carburizing", "steel-by-crucible"}
        assert "forge-steel-spear" in body["used_by"]

    def test_need(self, client):
        body = client.get("/api/need/cut:granite").json()
        assert body["tree"]["type"] == "action"

    def test_explore_with_hypothetical(self, client):
        body = client.post("/api/explore", json={"profile": "middle-kingdom-egypt", "hypothetical": ["hematite"]}).json()
        assert "steel" in body["reachable"]

    def test_check_by_id_and_inline(self, client):
        by_id = client.post("/api/check", json={"job": "granite-slab-saw-cut", "profile": "middle-kingdom-egypt"}).json()
        inline = client.post("/api/check", json={
            "profile": "middle-kingdom-egypt",
            "job_spec": {"verb": "shape", "target": "granite", "parameters": {"volume_cm3": 216}},
        }).json()
        assert by_id["steps"][0]["best"] == "cut-abrasive-saw"
        assert inline["steps"][0]["routes"][0]["hours"] == [1.0, 1.0]

    def test_profiles_include_what_the_dropdown_shows(self, client):
        profile = next(p for p in client.get("/api/profiles").json() if p["id"] == "middle-kingdom-egypt")
        assert profile["label"] == "Middle Kingdom Egypt"
        assert profile["description"]

    def test_graph_has_levels_and_can_draw_extra_actions(self, client):
        plain = client.get("/api/graph").json()
        steel = next(n for n in plain["nodes"] if n["id"] == "steel")
        extra = client.get("/api/graph", params={"action": ["cut:limestone"]}).json()
        assert steel["level"] == 8
        assert "cut:limestone" in {n["id"] for n in extra["nodes"]}
        assert "cut:limestone" in {a["id"] for a in plain["actions"]}

    def test_explore_includes_statuses_and_implied_by(self, client):
        body = client.post("/api/explore", json={"profile": "middle-kingdom-egypt"}).json()
        assert body["status"]["crucible"] == "implied"
        assert "tin-bronze" in body["implied_by"]["crucible"]

    def test_explain_with_and_without_everything(self, client):
        request = {"profile": "middle-kingdom-egypt", "node": "steel"}
        brief = client.post("/api/explain", json=request).json()
        full = client.post("/api/explain", json={**request, "all": True}).json()
        assert brief["status"] == "near" and "all" not in brief
        assert [row["id"] for row in full["all"]["missing"]] == ["bloom-iron", "iron-ore"]
        assert brief["about"]["description"] and brief["leads_to"]

    def test_explain_edge(self, client):
        body = client.post("/api/explain-edge", json={"profile": "middle-kingdom-egypt", "source": "heat", "target": "steel"}).json()
        assert body["kind"] == "requires" and len(body["routes"]) == 2

    def test_interactive_docs_stay_at_the_root(self, client):
        assert client.get("/docs").status_code == 200

    @pytest.mark.parametrize(
        ("method", "path", "payload", "status"),
        [
            ("get", "/api/nodes/unobtainium", None, 404),
            ("get", "/api/need/unobtainium", None, 404),
            ("post", "/api/explore", {"profile": "atlantis"}, 404),
            ("post", "/api/explore", {"select": ["unobtainium"]}, 422),
            ("post", "/api/check", {}, 422),
            ("post", "/api/explain", {"node": "unobtainium"}, 404),
            ("post", "/api/explain", {"node": "bloomery-smelting"}, 404),
            ("post", "/api/explain", {}, 422),
            ("post", "/api/explain-edge", {"source": "wood", "target": "steel"}, 404),
            ("post", "/api/explain-edge", {"source": "wood"}, 422),
            ("get", "/api/graph?action=bogus", None, 422),
            ("get", "/api/graph?action=fly:granite", None, 422),
            ("post", "/explore", {}, 404),
        ],
    )
    def test_errors(self, client, method, path, payload, status):
        response = client.request(method, path, json=payload)
        assert response.status_code == status


class TestWebUi:
    def test_serves_the_built_page_at_the_root_without_shadowing_the_api(self, repo_root, tmp_path):
        # given: a built web app
        (tmp_path / "index.html").write_text("<!doctype html><title>Capabilities UI</title>")
        (tmp_path / "assets").mkdir()
        (tmp_path / "assets" / "app.js").write_text("console.log('hi')")
        client = TestClient(create_app(repo_root, web_dist=tmp_path))
        # then: the page and its assets load, and the API and docs still answer
        assert "Capabilities UI" in client.get("/").text
        assert client.get("/assets/app.js").status_code == 200
        assert client.get("/api/health").json()["status"] == "ok"
        assert client.get("/docs").status_code == 200

    def test_explains_how_to_build_the_page_when_it_is_missing(self, repo_root, tmp_path):
        client = TestClient(create_app(repo_root, web_dist=tmp_path / "missing"))
        page = client.get("/")
        assert page.status_code == 200
        assert "npm run build" in page.text


class TestOccurrences:
    @pytest.fixture(scope="class")
    def mapped(self, repo_root, upstream_built_dir, tmp_path_factory) -> TestClient:
        """A server on a build with the 14-record MRDS sample."""
        return TestClient(create_app(repo_root, web_dist=tmp_path_factory.mktemp("no-web-build"), build_dir=upstream_built_dir))

    def test_a_materials_places_are_the_occurrences_of_its_sources_as_geojson(self, mapped, graph):
        body = mapped.get("/api/occurrences/hematite").json()
        assert body["sources"] == [
            {
                "id": "hematite-deposit", "label": "Hematite deposit", "availability": "regional",
                "regions": graph.things["hematite-deposit"]["regions"], "places": 3, "worked": 1, "class_level": False,
            },
            # And the ancient iron mines of Pleiades, which don't say which ore (ADR 0046): Dognecea, in the sample.
            {"id": "iron-ore", "label": "Iron ore", "availability": None, "regions": [], "places": 1, "worked": 1,
             "class_level": True},
        ]
        records = {f["properties"]["record_id"]: f for f in body["features"]["features"]}
        assert set(records) == {"10001442", "10003682", "10008106", "207083"}
        assert records["10008106"]["geometry"] == {"type": "Point", "coordinates": [-106.26, 39.24]}
        assert records["10008106"]["properties"]["worked_by_year"] == 1860
        assert records["207083"]["properties"]["class_level"] is True
        assert [dataset["id"] for dataset in body["datasets"]] == ["mrds", "pleiades"]

    def test_large_answers_are_compressed(self, mapped):
        response = mapped.get("/api/occurrences/hematite", headers={"Accept-Encoding": "gzip"})
        assert response.headers["content-encoding"] == "gzip"

    def test_with_nothing_downloaded_the_places_come_from_the_cold_backup(self, client):
        body = client.get("/api/occurrences/hematite").json()
        assert sum(source["places"] for source in body["sources"]) == len(body["features"]["features"]) > 0
        assert [dataset["id"] for dataset in body["datasets"]] == ["mrds", "pleiades"]

    def test_only_materials_and_sources_have_places(self, client):
        assert client.get("/api/occurrences/copper-saw").status_code == 404


class TestProfilePlaces:
    """A profile in space and time (ADR 0052): Middle Kingdom Egypt, on the Cliopatria and Pleiades samples."""

    @pytest.fixture(scope="class")
    def mapped(self, repo_root, upstream_built_dir, tmp_path_factory) -> TestClient:
        return TestClient(create_app(repo_root, web_dist=tmp_path_factory.mktemp("no-web-build"), build_dir=upstream_built_dir))

    def test_a_profile_says_where_it_is_and_what_was_found_there(self, mapped):
        place = mapped.get("/api/profiles/middle-kingdom-egypt").json()["map"]
        assert (place["cliopatria"], place["years"], place["release"]) == ("Middle Kingdom of Egypt", [-2050, -1650], "v0.2.2")
        assert place["area"]["type"] in ("Polygon", "MultiPolygon")
        granite = next(source for source in place["sources"] if source["id"] == "granite-outcrop")
        # Aswan's quarry was worked by 1086 BCE, after the Middle Kingdom: a maybe, which the profile lists anyway.
        assert (granite["availability"], granite["listed"], granite["from_map"]) == ("maybe", True, False)

    def test_a_places_map_marks_which_are_inside_the_profiles_area(self, mapped):
        body = mapped.get("/api/occurrences/granite", params={"profile": "middle-kingdom-egypt"}).json()
        assert body["profile"]["years"] == [-2050, -1650]
        inside = {f["properties"]["name"] for f in body["features"]["features"] if f["properties"]["in_area"]}
        assert "Aswan Quarry Landscape" in inside
        assert all("in_area" not in f["properties"] for f in mapped.get("/api/occurrences/granite").json()["features"]["features"])

    def test_an_unknown_profile_is_not_found(self, mapped):
        assert mapped.get("/api/occurrences/granite", params={"profile": "atlantis"}).status_code == 404

    def test_explore_names_the_sources_the_map_added_and_none_for_a_list_only(self, mapped):
        # Nothing is worked inside Middle Kingdom Egypt by 1650 BCE in the samples: the map adds nothing.
        assert mapped.post("/api/explore", json={"profile": "middle-kingdom-egypt"}).json()["from_map"] == []
        assert mapped.post("/api/explore", json={"select": ["copper"]}).json()["from_map"] == []


class TestProvenance:
    @pytest.fixture(scope="class")
    def upstream(self, repo_root, upstream_built_dir, tmp_path_factory) -> TestClient:
        """A server on a build with the Wikidata sample, in which granite's hardness comes from Wikidata."""
        return TestClient(create_app(repo_root, web_dist=tmp_path_factory.mktemp("no-web-build"), build_dir=upstream_built_dir))

    def hardness(self, client: TestClient, node: str) -> dict:
        about = client.post("/api/explain", json={"profile": "middle-kingdom-egypt", "node": node}).json()["about"]
        return next(quantity for quantity in about["quantities"] if quantity["id"] == "hardness_mohs")

    def test_an_upstream_value_names_its_dataset_and_record(self, upstream):
        granite = self.hardness(upstream, "granite")
        assert granite["value"] == "5–7 Mohs"
        assert granite["source"]["layer"] == "upstream"
        assert granite["source"]["upstream"]["dataset"] == "Wikidata"
        assert granite["source"]["upstream"]["url"] == "https://www.wikidata.org/wiki/Q41177"

    def test_an_upstream_value_that_agrees_shows_no_curated_value(self, upstream):
        # The curated layer matches Wikidata (ADR 0043), so there is nothing to show beside it; the views' tests cover a
        # value that disagrees.
        assert "curated_value" not in self.hardness(upstream, "granite")["source"]

    def test_a_curated_value_says_so(self, client):
        # Flint has no Wikidata hardness, so its value is curated.
        assert self.hardness(client, "flint")["source"] == {"layer": "curated"}
