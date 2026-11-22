import pytest
from dagster import AssetKey, materialize

from capabilities.built import is_current, load_built
from capabilities.graph import Graph

RAW = AssetKey(["raw", "curated_documents"])
STAGING = AssetKey("stg_curated__documents")
NODES = AssetKey("graph_nodes")
MANIFEST = AssetKey("graph_manifest")


@pytest.fixture
def dagster_build(repo_root, tmp_path, monkeypatch):
    """The Dagster definitions for the repository, building into a temporary directory."""
    # dbt reads these from the environment; monkeypatch puts them back afterwards.
    for name in ("CAPABILITIES_BUILD_DIR", "DBT_LOG_PATH", "DBT_TARGET_PATH", "DO_NOT_TRACK"):
        monkeypatch.delenv(name, raising=False)
    from capabilities_pipeline.assets import definitions

    build_dir = tmp_path / "build"
    return definitions(repo_root, build_dir), build_dir


def asset_graph(defs):
    return defs.resolve_asset_graph()


class TestDefinitions:
    def test_the_lineage_runs_from_the_curated_load_through_dbt_to_the_manifest(self, dagster_build):
        graph = asset_graph(dagster_build[0])
        assert graph.get(STAGING).parent_keys == {RAW}
        assert graph.get(NODES).parent_keys == {STAGING}
        assert graph.get(MANIFEST).parent_keys == {NODES}

    def test_assets_are_grouped_by_layer(self, dagster_build):
        graph = asset_graph(dagster_build[0])
        assert {key: graph.get(key).group_name for key in (RAW, STAGING, NODES, MANIFEST)} == {
            RAW: "raw", STAGING: "staging", NODES: "marts", MANIFEST: "marts",
        }

    def test_dbt_tests_on_sources_and_models_are_asset_checks(self, dagster_build):
        checks = {(key.asset_key, key.name) for key in asset_graph(dagster_build[0]).asset_check_keys}
        assert (RAW, "source_unique_raw_curated_documents_path") in checks
        assert (NODES, "unique_graph_nodes_id") in checks


class TestMaterializing:
    def test_materializing_everything_builds_a_current_graph_equal_to_the_curated_one(self, dagster_build, repo_root):
        defs, build_dir = dagster_build
        result = materialize(list(defs.assets), resources=defs.resources)
        assert result.success
        assert all(evaluation.passed for evaluation in result.get_asset_check_evaluations())
        assert is_current(repo_root, build_dir)
        built, curated = load_built(repo_root, build_dir), Graph.from_curated(repo_root)
        assert list(built.things.items()) == list(curated.things.items())
        assert list(built.routes.items()) == list(curated.routes.items())
