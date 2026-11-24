import csv
import json

import duckdb
import pytest

from capabilities.built import (
    FACTS_FILE,
    MANIFEST_FILE,
    NODES_FILE,
    current_graph,
    fingerprint,
    graph_dir,
    is_current,
    load_built,
)
from capabilities.graph import Graph
from capabilities_pipeline.build import BuildError, build, load_inputs, run_dbt, write_manifest

BUCKETS = ("quantities", "things", "verbs", "routes", "profiles", "jobs")


class TestBuiltGraph:
    def test_the_built_graph_has_the_curated_documents_in_the_same_order(self, repo_root, built_dir):
        curated, built = Graph.from_curated(repo_root), load_built(repo_root, built_dir)
        for bucket in BUCKETS:
            # The same documents in the same order (some answers list things in load order), except that a thing's
            # quantities are the values graph_facts chose.
            # Upstream nodes (ADR 0045) come after the curated ones.
            curated_ids = getattr(curated, bucket)
            without_quantities = lambda graph: [  # noqa: E731
                (node_id, {key: value for key, value in document.items() if key != "quantities"})
                for node_id, document in getattr(graph, bucket).items() if node_id in curated_ids
            ]
            assert without_quantities(built) == without_quantities(curated), bucket
            assert list(getattr(built, bucket))[: len(curated_ids)] == list(curated_ids), bucket

    def test_a_things_quantities_are_the_values_its_facts_chose(self, repo_root, built_dir):
        rows = duckdb.sql(
            "select node_id, split_part(field, '.', 2), value::varchar from read_parquet(?) where id is not null",
            params=[str(graph_dir(built_dir) / FACTS_FILE)],
        ).fetchall()
        chosen: dict[str, dict] = {}
        for node_id, quantity, value in rows:
            chosen.setdefault(node_id, {})[quantity] = json.loads(value)
        built = load_built(repo_root, built_dir)
        assert {thing: doc["quantities"] for thing, doc in built.things.items() if doc.get("quantities")} == chosen
        # Hematite's hardness comes only from Wikidata, through the cold backup.
        assert built.things["hematite"]["quantities"]["hardness_mohs"] == [5.5, 6.5]

    def test_every_node_says_it_came_from_the_curated_layer_and_which_file(self, built_dir):
        rows = duckdb.sql(
            "select id, provenance::varchar from read_parquet(?)", params=[str(graph_dir(built_dir) / NODES_FILE)]
        ).fetchall()
        provenance = {node_id: json.loads(value) for node_id, value in rows}
        assert provenance["quarry-granite"] == {"layer": "curated", "path": "data/routes/quarry-granite.yaml"}
        # Every other node is an upstream ore mineral, its deposit or its mining route, each saying where it came from:
        # the mineral from its Wikidata item, the deposit's places from MRDS, the route from the template it copies.
        assert {value["layer"] for value in provenance.values()} == {"curated", "upstream"}
        assert (provenance["azurite"]["dataset"], provenance["azurite"]["record"]) == ("wikidata", "Q108212")
        assert (provenance["azurite-deposit"]["dataset"], provenance["azurite-deposit"]["record"]) == (
            "mrds", "deposits listing Azurite as an ore mineral",
        )
        assert provenance["mine-azurite"]["copied_from"] == "mine-malachite"
        assert {value["crosswalk"] for value in provenance.values() if value["layer"] == "upstream"} == {
            "data/crosswalks/ore_minerals.csv",
        }

    def test_the_manifest_records_the_inputs_and_how_many_nodes(self, repo_root, built_dir):
        manifest = json.loads((graph_dir(built_dir) / MANIFEST_FILE).read_text())
        assert manifest["fingerprint"] == fingerprint(repo_root, built_dir)
        curated = Graph.from_curated(repo_root)
        with (repo_root / "data" / "crosswalks" / "ore_minerals.csv").open(newline="", encoding="utf-8") as file:
            minerals = sum(1 for row in csv.DictReader(file) if row["class"] != "none")
        # Each upstream ore mineral is three nodes: the mineral, its deposit and its mining route (ADR 0045).
        assert manifest["tables"][NODES_FILE] == sum(len(getattr(curated, bucket)) for bucket in BUCKETS) + 3 * minerals


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


    def test_an_edit_made_while_the_graph_builds_leaves_it_stale(self, data_copy, tmp_path):
        build_dir = tmp_path / "build"
        load_inputs(data_copy, build_dir)
        route = data_copy / "data" / "routes" / "quarry-granite.yaml"
        route.write_text(route.read_text() + "\n# edited after loading\n")
        run_dbt(build_dir)
        write_manifest(data_copy, build_dir)
        # The manifest records the inputs that were loaded, so the edit isn't in the graph and it isn't current.
        assert not is_current(data_copy, build_dir)


class TestBuildFailures:
    def test_an_id_shared_by_two_kinds_of_node_fails_the_build_and_leaves_nothing_current(self, data_copy, tmp_path):
        # A thing named like a route: each file is valid on its own, so only the build's uniqueness test catches it.
        clash = data_copy / "data" / "things" / "artifacts" / "quarry-granite.yaml"
        clash.write_text("id: quarry-granite\nkind: artifact\nlabel: Quarry granite\n")
        with pytest.raises(BuildError, match="unique"):
            build(data_copy, tmp_path / "build")
        assert not is_current(data_copy, tmp_path / "build")
