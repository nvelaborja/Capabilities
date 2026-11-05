import pytest
from fastapi.testclient import TestClient

from capabilities.server import create_app


@pytest.fixture(scope="module")
def client(repo_root) -> TestClient:
    return TestClient(create_app(repo_root))


class TestServer:
    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_nodes_can_be_filtered_by_kind(self, client):
        kinds = {node["kind"] for node in client.get("/nodes", params={"kind": "verb"}).json()}
        assert kinds == {"verb"}

    def test_node_detail_lists_routes(self, client):
        body = client.get("/nodes/steel").json()
        assert set(body["made_by"]) == {"steel-by-carburizing", "steel-by-crucible"}
        assert "forge-steel-spear" in body["used_by"]

    def test_need(self, client):
        body = client.get("/need/cut:granite").json()
        assert body["tree"]["type"] == "action"

    def test_explore_with_hypothetical(self, client):
        body = client.post("/explore", json={"profile": "middle-kingdom-egypt", "hypothetical": ["hematite"]}).json()
        assert "steel" in body["reachable"]

    def test_check_by_id_and_inline(self, client):
        by_id = client.post("/check", json={"job": "granite-slab-saw-cut", "profile": "middle-kingdom-egypt"}).json()
        inline = client.post("/check", json={
            "profile": "middle-kingdom-egypt",
            "job_spec": {"verb": "shape", "target": "granite", "parameters": {"volume_cm3": 216}},
        }).json()
        assert by_id["steps"][0]["best"] == "cut-abrasive-saw"
        assert inline["steps"][0]["routes"][0]["hours"] == [1.0, 1.0]

    @pytest.mark.parametrize(
        ("method", "path", "payload", "status"),
        [
            ("get", "/nodes/unobtainium", None, 404),
            ("get", "/need/unobtainium", None, 404),
            ("post", "/explore", {"profile": "atlantis"}, 404),
            ("post", "/explore", {"select": ["unobtainium"]}, 422),
            ("post", "/check", {}, 422),
        ],
    )
    def test_errors(self, client, method, path, payload, status):
        response = client.request(method, path, json=payload)
        assert response.status_code == status
