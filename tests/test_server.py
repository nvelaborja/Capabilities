import pytest
from fastapi.testclient import TestClient

from capabilities.server import create_app


@pytest.fixture(scope="module")
def client(repo_root, tmp_path_factory) -> TestClient:
    # Ignore any local web build so results don't depend on whether `npm run build` has been run.
    return TestClient(create_app(repo_root, web_dist=tmp_path_factory.mktemp("no-web-build")))


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
            ("post", "/api/explain", {"node": "iron-smelting"}, 404),
            ("post", "/api/explain", {}, 422),
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
