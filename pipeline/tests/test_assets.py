import json

import duckdb
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
FACTS = AssetKey("graph_facts")
WIKIDATA_SNAPSHOT = AssetKey(["upstream", "wikidata_quantities"])
WIKIDATA_RAW = AssetKey(["raw", "wikidata_quantities"])
WIKIDATA_STAGING = AssetKey("stg_wikidata__quantities")
WIKIDATA_CROSSWALK = AssetKey(["raw", "wikidata_things"])
SUPPRESSIONS = AssetKey(["raw", "suppressed_records"])
ORE_RAW = AssetKey(["raw", "ore_minerals"])
ORE_NODES = AssetKey("stg_ore_minerals__nodes")
ITEMS_SNAPSHOT = AssetKey(["upstream", "wikidata_items"])
PLEIADES_SNAPSHOT = AssetKey(["upstream", "pleiades_places"])
PLEIADES_RAW = AssetKey(["raw", "pleiades_places"])
PLEIADES_RULES = AssetKey(["raw", "pleiades_sources"])
PLEIADES_STAGING = AssetKey("stg_pleiades__workings")
PERIODS_SNAPSHOT = AssetKey(["upstream", "pleiades_periods"])
PERIODS_RAW = AssetKey(["raw", "pleiades_periods"])
PERIODS_STAGING = AssetKey("stg_pleiades__periods")
DATES_STAGING = AssetKey("stg_curated__dates")
ITEMS_RAW = AssetKey(["raw", "wikidata_items"])
CROSSWALKED_ITEMS = AssetKey("stg_crosswalk__wikidata_items")
QUEUE = AssetKey("curation_queue")
CHECKS = AssetKey("reference_checks")
REFERENCES_SNAPSHOT = AssetKey(["upstream", "reference_candidates"])
REFERENCES_RAW = AssetKey(["raw", "reference_candidates"])
CLIOPATRIA_SNAPSHOT = AssetKey(["upstream", "cliopatria_polities"])
CLIOPATRIA_RAW = AssetKey(["raw", "cliopatria_polities"])
CLIOPATRIA_STAGING = AssetKey("stg_cliopatria__polities")
PROFILE_PLACES = AssetKey("stg_curated__profile_places")
PROFILE_AREAS = AssetKey("profile_areas")
PROFILE_OCCURRENCES = AssetKey("profile_occurrences")
PROFILE_SOURCES = AssetKey("profile_sources")
SESHAT_SNAPSHOT = AssetKey(["upstream", "seshat_codings"])
SESHAT_RAW = AssetKey(["raw", "seshat_codings"])
SESHAT_STAGING = AssetKey("stg_seshat__codings")
SESHAT_VARIABLES = AssetKey(["raw", "seshat_variables"])
HISTORY = AssetKey("history_codings")
BACKTEST = AssetKey("backtest")


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
        assert graph.get(NODES).parent_keys == {STAGING, FACTS, ORE_NODES}
        assert graph.get(MANIFEST).parent_keys == {
            NODES, FACTS, OCCURRENCES, QUEUE, CHECKS, PROFILE_AREAS, PROFILE_OCCURRENCES, PROFILE_SOURCES, HISTORY}
        assert graph.get(REFERENCES_RAW).parent_keys == {REFERENCES_SNAPSHOT}

    def test_the_lineage_runs_from_the_mrds_download_and_the_crosswalk_to_the_occurrences(self, dagster_build):
        graph = asset_graph(dagster_build[0])
        assert graph.get(MRDS_RAW).parent_keys == {MRDS_SNAPSHOT}
        assert graph.get(MRDS_STAGING).parent_keys == {MRDS_RAW}
        assert graph.get(CROSSWALK).parent_keys == set()
        assert graph.get(OCCURRENCES).parent_keys == {
            MRDS_STAGING, CROSSWALK, ORE_RAW, SNAPSHOTS_RAW, SUPPRESSIONS, PLEIADES_STAGING, PLEIADES_RULES,
            PERIODS_STAGING, DATES_STAGING,
        }

    def test_the_lineage_runs_from_the_pleiades_download_and_its_rules_to_the_occurrences(self, dagster_build):
        graph = asset_graph(dagster_build[0])
        assert graph.get(PLEIADES_RAW).parent_keys == {PLEIADES_SNAPSHOT}
        assert graph.get(PLEIADES_STAGING).parent_keys == {PLEIADES_RAW}
        assert PLEIADES_STAGING in graph.get(QUEUE).parent_keys

    def test_the_lineage_runs_from_the_periods_download_and_the_curated_dates_to_the_occurrences(self, dagster_build):
        graph = asset_graph(dagster_build[0])
        assert graph.get(PERIODS_RAW).parent_keys == {PERIODS_SNAPSHOT}
        assert graph.get(PERIODS_STAGING).parent_keys == {PERIODS_RAW}
        assert {PERIODS_STAGING, DATES_STAGING} <= graph.get(OCCURRENCES).parent_keys

    def test_the_lineage_runs_from_the_cliopatria_download_and_the_profiles_to_their_sources(self, dagster_build):
        graph = asset_graph(dagster_build[0])
        assert graph.get(CLIOPATRIA_RAW).parent_keys == {CLIOPATRIA_SNAPSHOT}
        assert graph.get(CLIOPATRIA_STAGING).parent_keys == {CLIOPATRIA_RAW}
        assert graph.get(PROFILE_PLACES).parent_keys == {STAGING}
        assert {CLIOPATRIA_STAGING, PROFILE_PLACES, SNAPSHOTS_RAW} <= graph.get(PROFILE_AREAS).parent_keys
        assert graph.get(PROFILE_OCCURRENCES).parent_keys == {PROFILE_AREAS, OCCURRENCES}
        assert {PROFILE_OCCURRENCES, OCCURRENCES, NODES} <= graph.get(PROFILE_SOURCES).parent_keys
        assert {PROFILE_OCCURRENCES, PROFILE_SOURCES} <= graph.get(QUEUE).parent_keys

    def test_the_lineage_runs_from_the_seshat_download_through_generated_profiles_to_the_comparison(self, dagster_build):
        graph = asset_graph(dagster_build[0])
        assert graph.get(SESHAT_RAW).parent_keys == {SESHAT_SNAPSHOT}
        assert graph.get(SESHAT_STAGING).parent_keys == {SESHAT_RAW}
        assert SESHAT_STAGING in graph.get(PROFILE_AREAS).parent_keys
        assert {PROFILE_AREAS, SESHAT_STAGING, SESHAT_VARIABLES} <= graph.get(HISTORY).parent_keys
        assert graph.get(BACKTEST).parent_keys == {MANIFEST}

    def test_the_lineage_runs_from_the_wikidata_download_and_its_crosswalk_to_the_facts(self, dagster_build):
        graph = asset_graph(dagster_build[0])
        assert graph.get(WIKIDATA_RAW).parent_keys == {WIKIDATA_SNAPSHOT}
        assert graph.get(WIKIDATA_STAGING).parent_keys == {WIKIDATA_RAW}
        assert {WIKIDATA_STAGING, CROSSWALKED_ITEMS, SUPPRESSIONS, SNAPSHOTS_RAW} <= graph.get(FACTS).parent_keys
        assert graph.get(CROSSWALKED_ITEMS).parent_keys == {WIKIDATA_CROSSWALK, ORE_RAW}

    def test_the_lineage_runs_from_the_ore_crosswalk_and_wikidata_to_the_nodes_and_the_queue(self, dagster_build):
        graph = asset_graph(dagster_build[0])
        assert graph.get(ITEMS_RAW).parent_keys == {ITEMS_SNAPSHOT}
        assert {ORE_RAW, STAGING} <= graph.get(ORE_NODES).parent_keys
        assert {NODES, FACTS, OCCURRENCES, MRDS_STAGING} <= graph.get(QUEUE).parent_keys

    def test_assets_are_grouped_by_layer(self, dagster_build):
        graph = asset_graph(dagster_build[0])
        groups = {key: graph.get(key).group_name for key in (
            MRDS_SNAPSHOT, WIKIDATA_SNAPSHOT, RAW, MRDS_RAW, WIKIDATA_RAW, SNAPSHOTS_RAW, CROSSWALK, WIKIDATA_CROSSWALK,
            SUPPRESSIONS, STAGING, MRDS_STAGING, WIKIDATA_STAGING, NODES, FACTS, OCCURRENCES, MANIFEST,
            ITEMS_SNAPSHOT, ITEMS_RAW, ORE_RAW, ORE_NODES, CROSSWALKED_ITEMS, QUEUE,
        )}
        assert groups == {
            MRDS_SNAPSHOT: "upstream", WIKIDATA_SNAPSHOT: "upstream", ITEMS_SNAPSHOT: "upstream",
            RAW: "raw", MRDS_RAW: "raw", WIKIDATA_RAW: "raw", SNAPSHOTS_RAW: "raw", CROSSWALK: "raw",
            WIKIDATA_CROSSWALK: "raw", SUPPRESSIONS: "raw", ITEMS_RAW: "raw", ORE_RAW: "raw",
            STAGING: "staging", MRDS_STAGING: "staging", WIKIDATA_STAGING: "staging", ORE_NODES: "staging",
            CROSSWALKED_ITEMS: "staging",
            NODES: "marts", FACTS: "marts", OCCURRENCES: "marts", MANIFEST: "marts", QUEUE: "marts",
        }

    def test_dbt_tests_on_sources_and_models_are_asset_checks(self, dagster_build):
        checks = {(key.asset_key, key.name) for key in asset_graph(dagster_build[0]).asset_check_keys}
        assert (RAW, "source_unique_raw_curated_documents_path") in checks
        assert (MRDS_RAW, "source_unique_raw_mrds_deposits_dep_id") in checks
        assert (CROSSWALK, "source_not_null_raw_mrds_sources_source_id") in checks
        assert (NODES, "unique_graph_nodes_id") in checks
        assert (OCCURRENCES, "occurrences_are_valid_points") in checks
        assert (FACTS, "unique_graph_facts_id") in checks


class TestMaterializing:
    def test_materializing_everything_downloads_every_dataset_and_builds_a_current_graph(
        self, dagster_build, repo_root, tmp_path, mrds_zip, wikidata_endpoint, pleiades_gz, pleiades_periods_ttl,
        cliopatria_release, seshat_endpoint, scholarly_endpoint, lookups_offline,
    ):
        from capabilities_pipeline.assets import UpstreamDownloads

        defs, build_dir = dagster_build
        downloads = UpstreamDownloads(
            mrds_url=mrds_zip(tmp_path / "download"), wikidata_url=wikidata_endpoint.url, pleiades_url=pleiades_gz,
            pleiades_periods_url=pleiades_periods_ttl, openalex_url=scholarly_endpoint.openalex_url, crossref_url=scholarly_endpoint.crossref_url,
            cliopatria_url=cliopatria_release.url, cliopatria_archive=cliopatria_release.dataset.archive,
            seshat_url=seshat_endpoint.url, seshat_pause_s=0,
        )
        with lookups_offline():
            result = materialize(list(defs.assets), resources={**defs.resources, "downloads": downloads})
        assert result.success
        assert all(evaluation.passed for evaluation in result.get_asset_check_evaluations())
        assert is_current(repo_root, build_dir)
        built, curated = load_built(repo_root, build_dir), Graph.from_curated(repo_root)
        # The same things in the same order, with Wikidata's values where it has them (ADR 0043).
        assert list(built.things)[: len(curated.things)] == list(curated.things)  # then the upstream ore minerals
        assert built.things["granite"]["quantities"]["hardness_mohs"] == [5, 7]
        assert list(built.routes.items())[: len(curated.routes)] == list(curated.routes.items())
        manifest = json.loads((graph_dir(build_dir) / MANIFEST_FILE).read_text())
        # All fourteen MRDS sample records are placed: eleven occurrences of curated source kinds, and seven of upstream
        # ore minerals' deposits (ADR 0045). Nine of the thirteen Pleiades places match a rule, fifteen times: a copper
        # mine is a place of both copper ore classes (ADR 0046).
        assert manifest["tables"][OCCURRENCES_FILE] == 18 + 15
        assert manifest["upstream"]["pleiades_places"]["rows"] == 13
        assert manifest["upstream"]["pleiades_periods"]["rows"] == 26
        assert (manifest["upstream"]["cliopatria_polities"]["rows"], manifest["upstream"]["cliopatria_polities"]["release"]) == (5, "v0.2.2")
        origins = dict(duckdb.sql("select origin, count(*) from read_parquet(?) where id is not null group by origin",
                                  params=[str(graph_dir(build_dir) / "profile_areas.parquet")]).fetchall())
        assert origins["curated"] == sum("place" in profile for profile in curated.profiles.values())
        assert manifest["tables"]["profile_areas.parquet"] == sum(origins.values())
        assert manifest["upstream"]["mrds_deposits"]["rows"] == 14
        assert manifest["upstream"]["wikidata_quantities"]["rows"] == 4
        materialized = {event.asset_key for event in result.get_asset_materialization_events()}
        assert {RAW, CROSSWALK, MRDS_RAW, SNAPSHOTS_RAW, MRDS_SNAPSHOT, OCCURRENCES, MANIFEST} <= materialized
        assert {WIKIDATA_SNAPSHOT, WIKIDATA_RAW, WIKIDATA_CROSSWALK, SUPPRESSIONS, FACTS} <= materialized
        assert {ITEMS_SNAPSHOT, ITEMS_RAW, ORE_RAW, ORE_NODES, QUEUE} <= materialized
        assert {PLEIADES_SNAPSHOT, PLEIADES_RAW, PLEIADES_RULES, PLEIADES_STAGING} <= materialized
        assert {PERIODS_SNAPSHOT, PERIODS_RAW, PERIODS_STAGING} <= materialized
        assert {CLIOPATRIA_SNAPSHOT, CLIOPATRIA_RAW, CLIOPATRIA_STAGING, PROFILE_AREAS, PROFILE_SOURCES} <= materialized
        assert {SESHAT_SNAPSHOT, SESHAT_RAW, SESHAT_STAGING, HISTORY, BACKTEST} <= materialized
        backtest = next(event for event in result.get_asset_materialization_events() if event.asset_key == BACKTEST)
        summary = json.loads((graph_dir(build_dir) / "backtest.json").read_text())
        assert backtest.materialization.metadata["polities"].value == summary["polities"] > 0
        assert summary["fingerprint"] == manifest["fingerprint"]
        # The run says which Cliopatria release it downloaded, and from where (ADR 0052).
        cliopatria = next(event for event in result.get_asset_materialization_events() if event.asset_key == CLIOPATRIA_SNAPSHOT)
        metadata = cliopatria.materialization.metadata
        assert metadata["release"].value == "v0.2.2" and metadata["archive"].value.endswith("/v0.2.2/cliopatria.geojson.zip")
        assert {REFERENCES_SNAPSHOT, REFERENCES_RAW, CHECKS} <= materialized

    def test_offline_a_download_falls_back_to_the_cold_backup_and_says_so(self, dagster_build, wikidata_endpoint):
        from capabilities_pipeline.assets import UpstreamDownloads

        defs, _ = dagster_build
        # Port 9 refuses connections, as a server that is down or a network that is off would.
        downloads = UpstreamDownloads(mrds_url="http://127.0.0.1:9/mrds-csv.zip", wikidata_url=wikidata_endpoint.url)
        snapshots = [asset for asset in defs.assets if MRDS_SNAPSHOT in asset.keys]
        result = materialize(snapshots, resources={**defs.resources, "downloads": downloads})
        assert result.success
        (event,) = result.get_asset_materialization_events()
        metadata = event.materialization.metadata
        assert metadata["copy"].value == "backup"
        assert "download_error" in metadata
