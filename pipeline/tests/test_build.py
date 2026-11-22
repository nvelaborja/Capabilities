import json

import duckdb
import pytest

from capabilities.built import (
    MANIFEST_FILE,
    NODES_FILE,
    current_graph,
    fingerprint,
    graph_dir,
    is_current,
    load_built,
)
from capabilities.graph import Graph
from capabilities.reasoner import Selection, explore
from capabilities_pipeline.build import BuildError, build

BUCKETS = ("quantities", "things", "verbs", "routes", "profiles", "jobs")


class TestBuiltGraph:
    def test_the_built_graph_is_the_curated_graph_in_the_same_order(self, repo_root, built_dir):
        curated, built = Graph.from_curated(repo_root), load_built(repo_root, built_dir)
        for bucket in BUCKETS:
            # Same documents and the same order: some answers list things in load order.
            assert list(getattr(built, bucket).items()) == list(getattr(curated, bucket).items()), bucket

    def test_answers_from_the_built_graph_match_the_curated_graph(self, repo_root, built_dir):
        # The worked example in examples/README.md: Middle Kingdom Egypt, plus hematite as a what-if.
        def egypt(graph):
            selected = Selection.from_profile(graph.profiles["middle-kingdom-egypt"])
            return explore(graph, selected, Selection.parse(["hematite"])).to_dict(graph)

        assert egypt(load_built(repo_root, built_dir)) == egypt(Graph.from_curated(repo_root))

    def test_every_node_says_it_came_from_the_curated_layer_and_which_file(self, built_dir):
        rows = duckdb.sql(
            "select id, provenance::varchar from read_parquet(?)", params=[str(graph_dir(built_dir) / NODES_FILE)]
        ).fetchall()
        provenance = {node_id: json.loads(value) for node_id, value in rows}
        assert provenance["quarry-granite"] == {"layer": "curated", "path": "data/routes/quarry-granite.yaml"}
        assert {value["layer"] for value in provenance.values()} == {"curated"}

    def test_the_manifest_records_the_inputs_and_how_many_nodes(self, repo_root, built_dir):
        manifest = json.loads((graph_dir(built_dir) / MANIFEST_FILE).read_text())
        assert manifest["fingerprint"] == fingerprint(repo_root)
        curated = Graph.from_curated(repo_root)
        assert manifest["tables"][NODES_FILE] == sum(len(getattr(curated, bucket)) for bucket in BUCKETS)


class TestFreshness:
    def test_a_fresh_build_is_current(self, repo_root, built_dir):
        assert is_current(repo_root, built_dir)

    def test_editing_any_data_file_changes_the_fingerprint(self, data_copy):
        before = fingerprint(data_copy)
        route = data_copy / "data" / "routes" / "quarry-granite.yaml"
        route.write_text(route.read_text() + "\n# edited\n")
        assert fingerprint(data_copy) != before

    def test_a_build_from_other_inputs_is_not_current(self, data_copy, built_dir, tmp_path):
        (data_copy / "data" / "routes" / "quarry-granite.yaml").write_text(
            (data_copy / "data" / "routes" / "quarry-granite.yaml").read_text() + "\n# edited\n"
        )
        assert not is_current(data_copy, built_dir)
        assert not is_current(data_copy, tmp_path / "never-built")

    def test_a_stale_graph_is_rebuilt_before_it_is_read(self, data_copy, tmp_path, capsys):
        build_dir = tmp_path / "build"
        graph = current_graph(data_copy, build_dir)
        assert "building it now" in capsys.readouterr().err
        assert is_current(data_copy, build_dir)
        assert "quarry-granite" in graph.routes


class TestBuildFailures:
    def test_an_id_shared_by_two_kinds_of_node_fails_the_build_and_leaves_nothing_current(self, data_copy, tmp_path):
        # A thing named like a route: each file is valid on its own, so only the build's uniqueness test catches it.
        clash = data_copy / "data" / "things" / "artifacts" / "quarry-granite.yaml"
        clash.write_text("id: quarry-granite\nkind: artifact\nlabel: Quarry granite\n")
        with pytest.raises(BuildError, match="unique"):
            build(data_copy, tmp_path / "build")
        assert not is_current(data_copy, tmp_path / "build")
