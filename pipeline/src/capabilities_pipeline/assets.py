"""The build as Dagster assets: upstream downloads, the load into raw tables, every dbt model (their data tests become
asset checks), and the manifest.

`capabilities build` runs the same load, dbt and manifest steps without Dagster (build.py), using whatever upstream
snapshots were downloaded before. definitions.py is what Dagster loads.

Agent runs (ADR 0048) are a job, `agent_curation`, not an asset: a run is started by hand with its size, never by
materializing everything.
"""

# No `from __future__ import annotations`: Dagster inspects the `context` annotation at definition time.
from dataclasses import replace
from pathlib import Path

from capabilities.built import CHECKS_FILE, FACTS_FILE, NODES_FILE, OCCURRENCES_FILE, QUEUE_FILE, graph_dir
from dagster import (
    AssetExecutionContext,
    AssetKey,
    AssetSpec,
    Config,
    ConfigurableResource,
    Definitions,
    MaterializeResult,
    OpExecutionContext,
    asset,
    job,
    multi_asset,
    op,
)
from dagster_dbt import (
    DagsterDbtTranslator,
    DagsterDbtTranslatorSettings,
    DbtCliResource,
    DbtProject,
    dbt_assets,
    get_asset_key_for_model,
    get_asset_keys_by_output_name_for_source,
)

from .agents.branch import Downloads
from .agents.curate import Settings
from .agents.run import run_ore_candidates
from .build import DBT_PROJECT, dbt_environment, dbt_target_path, load_inputs, write_manifest
from .upstream import MRDS, PLEIADES, REFERENCES, WIKIDATA, WIKIDATA_ITEMS, Dataset, fetch_or_fall_back


class UpstreamDownloads(ConfigurableResource):
    """Where each upstream dataset is downloaded from. Tests point it at a local file."""

    mrds_url: str = MRDS.url
    wikidata_url: str = WIKIDATA.url
    pleiades_url: str = PLEIADES.url
    openalex_url: str = REFERENCES.url
    crossref_url: str = REFERENCES.crossref_url


class AgentRunConfig(Config):
    """One agent run's size and settings (ADR 0048). Launched by hand:

        cd pipeline && uv run dg launch --job agent_curation --config-json \\
            '{"ops": {"curate_ore_candidates": {"config": {"items": 5}}}}'
    """

    items: int = 5  # how many queue items to work through, most widely listed first
    evaluate: bool = False  # ask again about the minerals a person decided, score the answers, open no pull request
    proposer_model: str = "opus"
    reviewer_model: str = "opus"
    proposer_effort: str | None = None  # low, medium, high, xhigh or max; unset is Claude Code's default
    reviewer_effort: str | None = None
    # Stop before the next item once the plan's five-hour or weekly usage reaches this share.
    stop_at_five_hour: float = 0.8
    stop_at_seven_day: float = 0.9
    pull_request: bool = True
    base: str = "origin/main"


def definitions(root: Path, build_dir: Path) -> Definitions:
    dbt_environment(build_dir)
    project = DbtProject(DBT_PROJECT, target_path=dbt_target_path(build_dir))
    # Dagster reads the dbt project's shape from its manifest. Parsing takes a few seconds, and doing it on every load
    # means a new or renamed model shows up without a separate step.
    project.preparer.prepare(project)

    # Source tests (on the raw tables) become checks on the assets that load them, like the models' own tests.
    translator = DagsterDbtTranslator(settings=DagsterDbtTranslatorSettings(enable_source_tests_as_checks=True))

    @dbt_assets(manifest=project.manifest_path, project=project, dagster_dbt_translator=translator)
    def graph_models(context: AssetExecutionContext, dbt: DbtCliResource):
        yield from dbt.cli(["build"], context=context).stream()

    @asset(
        key=AssetKey(["upstream", MRDS.name]),
        group_name="upstream",
        description="A snapshot of the USGS Mineral Resources Data System (MRDS): downloaded, converted to Parquet "
        "unchanged, and recorded with its retrieval time, hash and license (ADR 0041).",
    )
    def mrds_snapshot(context: AssetExecutionContext, downloads: UpstreamDownloads) -> MaterializeResult:
        return download(context, MRDS, downloads.mrds_url)

    @asset(
        key=AssetKey(["upstream", WIKIDATA.name]),
        group_name="upstream",
        description="A snapshot of Wikidata's quantity statements (such as Mohs hardness) for the items in the Wikidata "
        "crosswalk: a SPARQL query, its result kept unchanged as Parquet, with the query itself (ADR 0043).",
    )
    def wikidata_snapshot(context: AssetExecutionContext, downloads: UpstreamDownloads) -> MaterializeResult:
        return download(context, WIKIDATA, downloads.wikidata_url)

    @asset(
        key=AssetKey(["upstream", WIKIDATA_ITEMS.name]),
        group_name="upstream",
        description="A snapshot of the English label and description, and the chemical formula, of every crosswalked "
        "Wikidata item: what the upstream ore minerals are called and described with (ADR 0045).",
    )
    def wikidata_items_snapshot(context: AssetExecutionContext, downloads: UpstreamDownloads) -> MaterializeResult:
        return download(context, WIKIDATA_ITEMS, downloads.wikidata_url)

    @asset(
        key=AssetKey(["upstream", PLEIADES.name]),
        group_name="upstream",
        description="A snapshot of every place in Pleiades, the gazetteer of ancient places: the daily CSV dump, kept "
        "unchanged as Parquet. Its mines and quarries become occurrences, with the dates they are attested (ADR 0046).",
    )
    def pleiades_snapshot(context: AssetExecutionContext, downloads: UpstreamDownloads) -> MaterializeResult:
        return download(context, PLEIADES, downloads.pleiades_url)

    @asset(
        key=AssetKey(["upstream", REFERENCES.name]),
        group_name="upstream",
        description="What OpenAlex and Crossref hold for each work the curated layer cites (a few candidates each, by "
        "DOI or by searching), and whether each cited link still loads. dbt scores the candidates (ADR 0047).",
    )
    def reference_candidates_snapshot(context: AssetExecutionContext, downloads: UpstreamDownloads) -> MaterializeResult:
        return download(context, replace(REFERENCES, crossref_url=downloads.crossref_url), downloads.openalex_url)

    def download(context: AssetExecutionContext, dataset: Dataset, url: str) -> MaterializeResult:
        """Download a dataset. Offline, or when its server is down, the build goes on with the cold backup (ADR 0044),
        and the run says so: the asset's metadata names the copy used and the error."""
        snapshot, error = fetch_or_fall_back(dataset, root, build_dir, url)
        metadata = {key: snapshot[key] for key in ("rows", "retrieved_at", "sha256", "url", "license")}
        metadata["copy"] = snapshot.get("copy", "download")
        if error:
            context.log.warning(f"Couldn't download {dataset.name} ({error}); using the cold backup of {snapshot['retrieved_at']}.")
            metadata["download_error"] = error
        return MaterializeResult(metadata=metadata)

    # The raw tables are the dbt sources' assets, so the lineage runs from the inputs through every model.
    raw = {key.path[-1]: key for key in get_asset_keys_by_output_name_for_source([graph_models], "raw").values()}
    descriptions = {
        "curated_documents": "Every curated YAML document, whole, loaded into DuckDB with the fingerprint of the inputs.",
        "mrds_sources": "The hand-kept crosswalk from MRDS deposits to our source kinds (data/crosswalks).",
        "wikidata_things": "The hand-kept crosswalk from our things to Wikidata items (data/crosswalks).",
        "ore_minerals": "The hand-kept crosswalk of ore minerals that join the graph from upstream (data/crosswalks).",
        "suppressed_records": "Upstream records the curated layer leaves out, with why (data/suppressions).",
        MRDS.name: "The MRDS snapshot, loaded into DuckDB as text.",
        WIKIDATA.name: "The Wikidata quantities snapshot, loaded into DuckDB as text.",
        WIKIDATA_ITEMS.name: "The Wikidata items snapshot (labels, descriptions, formulas), loaded into DuckDB as text.",
        PLEIADES.name: "The Pleiades places snapshot, loaded into DuckDB as text.",
        REFERENCES.name: "What OpenAlex and Crossref hold for the works we cite, and our links' statuses, as text.",
        "pleiades_sources": "The hand-kept crosswalk of rules matching Pleiades mines and quarries to our sources and ore "
        "classes (data/crosswalks).",
        "upstream_snapshots": "Where and when each upstream snapshot was retrieved, and which copy was used, for provenance.",
    }

    downloads_behind = {
        MRDS.name: [mrds_snapshot],
        WIKIDATA.name: [wikidata_snapshot],
        WIKIDATA_ITEMS.name: [wikidata_items_snapshot],
        PLEIADES.name: [pleiades_snapshot],
        REFERENCES.name: [reference_candidates_snapshot],
        "upstream_snapshots": [mrds_snapshot, wikidata_snapshot, wikidata_items_snapshot, pleiades_snapshot,
                               reference_candidates_snapshot],
    }

    @multi_asset(
        specs=[
            AssetSpec(
                raw[name],
                group_name="raw",
                description=descriptions[name],
                deps=downloads_behind.get(name, []),
            )
            for name in descriptions
        ],
    )
    def raw_tables():
        """One step, as in `capabilities build`: the fingerprint must be taken once, before any input is read."""
        loaded = load_inputs(root, build_dir)
        yield MaterializeResult(asset_key=raw["curated_documents"], metadata={"documents": loaded["documents"]})
        yield MaterializeResult(asset_key=raw["mrds_sources"], metadata={"rules": loaded["crosswalks"]["mrds_sources"]})
        yield MaterializeResult(
            asset_key=raw["wikidata_things"], metadata={"matches": loaded["crosswalks"]["wikidata_things"]}
        )
        yield MaterializeResult(asset_key=raw["ore_minerals"], metadata={"rows": loaded["crosswalks"]["ore_minerals"]})
        yield MaterializeResult(
            asset_key=raw["suppressed_records"], metadata={"records": loaded["suppressions"]["suppressed_records"]}
        )
        yield MaterializeResult(
            asset_key=raw["pleiades_sources"], metadata={"rules": loaded["crosswalks"]["pleiades_sources"]}
        )
        for dataset in (MRDS, WIKIDATA, WIKIDATA_ITEMS, PLEIADES, REFERENCES):
            snapshot = loaded["upstream"][dataset.name]
            yield MaterializeResult(asset_key=raw[dataset.name], metadata={"rows": snapshot["rows"], "copy": snapshot["copy"]})
        yield MaterializeResult(asset_key=raw["upstream_snapshots"], metadata={"datasets": len(loaded["upstream"])})

    @asset(
        deps=[get_asset_key_for_model([graph_models], name) for name in ("graph_nodes", "graph_facts", "source_occurrences", "curation_queue", "reference_checks")],
        group_name="marts",
        description="graph/manifest.json: what the built graph was made from. The app reads only a build whose "
        "manifest matches its inputs (ADR 0038).",
    )
    def graph_manifest() -> MaterializeResult:
        manifest = write_manifest(root, build_dir)
        return MaterializeResult(
            metadata={
                "nodes": manifest["tables"][NODES_FILE],
                "facts": manifest["tables"][FACTS_FILE],
                "queue": manifest["tables"][QUEUE_FILE],
                "occurrences": manifest["tables"][OCCURRENCES_FILE],
                "reference_checks": manifest["tables"][CHECKS_FILE],
                "fingerprint": manifest["fingerprint"],
                "path": str(graph_dir(build_dir)),
            }
        )

    @op(description="Agents propose ore crosswalk rows for the top ore candidates in the curation queue; code and a "
        "reviewer agent check them; what passes becomes a draft pull request (ADR 0035, ADR 0048). Uses Claude Code on "
        "your Claude login, so it draws on your plan's usage limits.")
    def curate_ore_candidates(context: OpExecutionContext, config: AgentRunConfig, downloads: UpstreamDownloads) -> dict:
        report = run_ore_candidates(
            root, build_dir, Settings(**config.model_dump()),
            Downloads(downloads.wikidata_url, downloads.openalex_url, downloads.crossref_url),
            on_progress=context.log.info,
        )
        usage = report.summary["usage"]
        metadata = {
            "run": report.run_id,
            "outcomes": report.summary["outcomes"],
            "stopped_because": report.stopped_because or "",
            "pull_request": report.pull_request or "",
            "calls": usage["calls"],
            "five_hour_usage": f"{usage['first_limits'].get('five_hour')} → {usage['limits'].get('five_hour')}",
            "seven_day_usage": f"{usage['first_limits'].get('seven_day')} → {usage['limits'].get('seven_day')}",
        }
        if "score" in report.summary:
            metadata["score"] = report.summary["score"]
        context.add_output_metadata(metadata)
        return report.summary

    @job(description="Started by hand only, with a size: agents work through the curation queue's ore candidates "
         "(ADR 0048).")
    def agent_curation():
        curate_ore_candidates()

    return Definitions(
        assets=[mrds_snapshot, wikidata_snapshot, wikidata_items_snapshot, pleiades_snapshot, reference_candidates_snapshot,
                raw_tables, graph_models, graph_manifest],
        jobs=[agent_curation],
        resources={"dbt": DbtCliResource(project_dir=project), "downloads": UpstreamDownloads()},
    )
