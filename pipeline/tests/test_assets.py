import json

import pytest
from dagster import AssetKey, materialize

from capabilities.built import MANIFEST_FILE, OCCURRENCES_FILE, graph_dir, is_current, load_built
from capabilities.graph import Graph

RAW = AssetKey(["raw", "curated_documents"])
STAGING = AssetKey("stg_curated__documents")
NODES = AssetKey("graph_nodes")
MANIFEST = AssetKey("graph_manifest")
MRDS_SNAPSHOT = AssetKey(["upstream", "mrds_deposits"])
MRDS_RAW = AssetKey(["raw", "mrds_deposits"])
SNAPSHOTS_RAW = AssetKey(["raw", "upstream_snapshots"])
MRDS_STAGING = AssetKey("stg_mrds__deposits")
CROSSWALK = AssetKey(["raw", "mrds_sources"])
OCCURRENCES = AssetKey("source_occurrences")


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
        assert graph.get(MANIFEST).parent_keys == {NODES, OCCURRENCES}

    def test_the_lineage_runs_from_the_mrds_download_and_the_crosswalk_to_the_occurrences(self, dagster_build):
        graph = asset_graph(dagster_build[0])
        assert graph.get(MRDS_RAW).parent_keys == {MRDS_SNAPSHOT}
        assert graph.get(MRDS_STAGING).parent_keys == {MRDS_RAW}
        assert graph.get(CROSSWALK).parent_keys == set()
        assert graph.get(OCCURRENCES).parent_keys == {MRDS_STAGING, CROSSWALK, SNAPSHOTS_RAW}

    def test_assets_are_grouped_by_layer(self, dagster_build):
        graph = asset_graph(dagster_build[0])
        groups = {key: graph.get(key).group_name for key in (
            MRDS_SNAPSHOT, RAW, MRDS_RAW, SNAPSHOTS_RAW, CROSSWALK, STAGING, MRDS_STAGING, NODES, OCCURRENCES, MANIFEST,
        )}
        assert groups == {
            MRDS_SNAPSHOT: "upstream",
            RAW: "raw", MRDS_RAW: "raw", SNAPSHOTS_RAW: "raw", CROSSWALK: "raw",
            STAGING: "staging", MRDS_STAGING: "staging",
            NODES: "marts", OCCURRENCES: "marts", MANIFEST: "marts",
        }

    def test_dbt_tests_on_sources_and_models_are_asset_checks(self, dagster_build):
        checks = {(key.asset_key, key.name) for key in asset_graph(dagster_build[0]).asset_check_keys}
        assert (RAW, "source_unique_raw_curated_documents_path") in checks
        assert (MRDS_RAW, "source_unique_raw_mrds_deposits_dep_id") in checks
        assert (CROSSWALK, "source_not_null_raw_mrds_sources_source_id") in checks
        assert (NODES, "unique_graph_nodes_id") in checks
        assert (OCCURRENCES, "occurrences_are_valid_points") in checks


class TestMaterializing:
    def test_materializing_everything_downloads_mrds_and_builds_a_current_graph(
        self, dagster_build, repo_root, tmp_path, mrds_zip
    ):
        from capabilities_pipeline.assets import UpstreamDownloads

        defs, build_dir = dagster_build
        downloads = UpstreamDownloads(mrds_url=mrds_zip(tmp_path / "download"))
        result = materialize(list(defs.assets), resources={**defs.resources, "downloads": downloads})
        assert result.success
        assert all(evaluation.passed for evaluation in result.get_asset_check_evaluations())
        assert is_current(repo_root, build_dir)
        built, curated = load_built(repo_root, build_dir), Graph.from_curated(repo_root)
        assert list(built.things.items()) == list(curated.things.items())
        assert list(built.routes.items()) == list(curated.routes.items())
        manifest = json.loads((graph_dir(build_dir) / MANIFEST_FILE).read_text())
        # All fourteen sample records are placed, and eleven occurrences match a source kind.
        assert manifest["tables"][OCCURRENCES_FILE] == 11
        assert manifest["upstream"]["mrds_deposits"]["rows"] == 14
        materialized = {event.asset_key for event in result.get_asset_materialization_events()}
        assert {RAW, CROSSWALK, MRDS_RAW, SNAPSHOTS_RAW, MRDS_SNAPSHOT, OCCURRENCES, MANIFEST} <= materialized
