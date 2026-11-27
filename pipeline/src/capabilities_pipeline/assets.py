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
from .agents.recheck import RecheckSettings, recheck as recheck_facts
from .agents.run import run_agents
from .build import DBT_PROJECT, dbt_environment, dbt_target_path, load_inputs, write_manifest
from .upstream import (CLIOPATRIA, MRDS, PLEIADES, PLEIADES_PERIODS, REFERENCES, REPORTS, WIKIDATA, WIKIDATA_ITEMS,
                       Dataset, fetch_or_fall_back)


class UpstreamDownloads(ConfigurableResource):
    """Where each upstream dataset is downloaded from. Tests point it at a local file."""

    mrds_url: str = MRDS.url
    wikidata_url: str = WIKIDATA.url
    pleiades_url: str = PLEIADES.url
    pleiades_periods_url: str = PLEIADES_PERIODS.url
    cliopatria_url: str = CLIOPATRIA.url  # the latest release
    cliopatria_archive: str = CLIOPATRIA.archive  # the zip at a release's tag
    openalex_url: str = REFERENCES.url
    crossref_url: str = REFERENCES.crossref_url
    github_reports_url: str = REPORTS.url
    wikidata_site_url: str = "https://www.wikidata.org"  # Wikidata's items and search, where agents' runs find minerals


class AgentRunConfig(Config):
    """One agent run's task, size and settings (ADR 0048, ADR 0049). Launched by hand:

        cd pipeline && uv run dg launch --job agent_curation --config-json \\
            '{"ops": {"curate": {"config": {"task": "route_sources", "items": 5}}}}'
    """

    task: str = "ore_candidates"  # ore_candidates (ADR 0048) or route_sources (ADR 0049)
    items: int = 5  # how many queue items to work through, in the queue's order
    evaluate: bool = False  # ask again about the items a person decided, score the answers, open no pull request
    proposer_model: str = "sonnet"  # chooses among passages code found (ADR 0048)
    reviewer_model: str = "sonnet"
    proposer_effort: str | None = "medium"  # low, medium, high, xhigh or max; unset is Claude Code's default
    reviewer_effort: str | None = "high"
    # Stop before the next item once the plan's five-hour or weekly usage reaches this share.
    stop_at_five_hour: float = 0.8
    stop_at_seven_day: float = 0.9
    pull_request: bool = True
    base: str = "origin/main"
    names: list[str] = []  # these items (minerals by MRDS name, routes by id), instead of the top of the queue
    find_only: bool = False  # find the items and passages, ask no model: what a run would offer, for none of the plan


class RecheckConfig(Config):
    """Which merged agent facts to check again, and how (ADR 0050). Launched by hand, by an admin:

        cd pipeline && uv run dg launch --job agent_recheck --config-json \\
            '{"ops": {"recheck": {"config": {"runs": ["ore-20261125-222345"]}}}}'
    """

    runs: list[str] = []  # the facts these runs proposed
    prompt_versions: list[str] = []  # or those of runs that used these prompts (their hashes, as summaries record them)
    models: list[str] = []  # or those of runs that used these models
    every_fact: bool = False  # or every merged agent fact
    reviewer: bool = False  # ask the reviewer agent again too: uses your Claude plan. Off, only code's free checks run
    reviewer_model: str = "sonnet"
    reviewer_effort: str | None = "high"
    stop_at_five_hour: float = 0.8
    stop_at_seven_day: float = 0.9
    report_failures: bool = False  # open a GitHub issue labelled `report` for each fact that doesn't hold


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
        key=AssetKey(["upstream", PLEIADES_PERIODS.name]),
        group_name="upstream",
        description="A snapshot of Pleiades' vocabulary of time periods (Turtle), read into each period's key, label and "
        "years. The end of a place's earliest period dates when a mine or quarry was worked by (ADR 0051).",
    )
    def pleiades_periods_snapshot(context: AssetExecutionContext, downloads: UpstreamDownloads) -> MaterializeResult:
        return download(context, PLEIADES_PERIODS, downloads.pleiades_periods_url)

    @asset(
        key=AssetKey(["upstream", CLIOPATRIA.name]),
        group_name="upstream",
        description="A snapshot of Cliopatria's latest release: the borders of the world's polities from 3400 BCE to "
        "2024 CE, each row an entity's polygons for a range of years. A profile's place is one of its entities, and its "
        "area the entity's polygons in the profile's years (ADR 0052).",
    )
    def cliopatria_snapshot(context: AssetExecutionContext, downloads: UpstreamDownloads) -> MaterializeResult:
        return download(context, replace(CLIOPATRIA, archive=downloads.cliopatria_archive), downloads.cliopatria_url)

    @asset(
        key=AssetKey(["upstream", REFERENCES.name]),
        group_name="upstream",
        description="What OpenAlex and Crossref hold for each work the curated layer cites (a few candidates each, by "
        "DOI or by searching), and whether each cited link still loads. dbt scores the candidates (ADR 0047).",
    )
    def reference_candidates_snapshot(context: AssetExecutionContext, downloads: UpstreamDownloads) -> MaterializeResult:
        return download(context, replace(REFERENCES, crossref_url=downloads.crossref_url), downloads.openalex_url)

    @asset(
        key=AssetKey(["upstream", REPORTS.name]),
        group_name="upstream",
        description="The repository's open GitHub issues labelled `report`: facts readers reported from the app's detail "
        "pane. Each joins the curation queue, first (ADR 0050).",
    )
    def github_reports_snapshot(context: AssetExecutionContext, downloads: UpstreamDownloads) -> MaterializeResult:
        return download(context, REPORTS, downloads.github_reports_url)

    def download(context: AssetExecutionContext, dataset: Dataset, url: str) -> MaterializeResult:
        """Download a dataset. Offline, or when its server is down, the build goes on with the cold backup (ADR 0044),
        and the run says so: the asset's metadata names the copy used and the error."""
        snapshot, error = fetch_or_fall_back(dataset, root, build_dir, url)
        metadata = {key: snapshot[key] for key in ("rows", "retrieved_at", "sha256", "url", "license")}
        # A dataset published in releases (Cliopatria) says which one, and the file it came from (ADR 0052).
        metadata |= {key: snapshot[key] for key in ("release", "archive") if snapshot.get(key)}
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
        PLEIADES_PERIODS.name: "The Pleiades time periods snapshot, loaded into DuckDB as text.",
        CLIOPATRIA.name: "The Cliopatria snapshot, loaded into DuckDB: properties as text, polygons as WKB.",
        REFERENCES.name: "What OpenAlex and Crossref hold for the works we cite, and our links' statuses, as text.",
        REPORTS.name: "The open reports from GitHub issues, as text.",
        "pleiades_sources": "The hand-kept crosswalk of rules matching Pleiades mines and quarries to our sources and ore "
        "classes (data/crosswalks).",
        "upstream_snapshots": "Where and when each upstream snapshot was retrieved, and which copy was used, for provenance.",
    }

    downloads_behind = {
        MRDS.name: [mrds_snapshot],
        WIKIDATA.name: [wikidata_snapshot],
        WIKIDATA_ITEMS.name: [wikidata_items_snapshot],
        PLEIADES.name: [pleiades_snapshot],
        PLEIADES_PERIODS.name: [pleiades_periods_snapshot],
        CLIOPATRIA.name: [cliopatria_snapshot],
        REFERENCES.name: [reference_candidates_snapshot],
        REPORTS.name: [github_reports_snapshot],
        "upstream_snapshots": [mrds_snapshot, wikidata_snapshot, wikidata_items_snapshot, pleiades_snapshot,
                               pleiades_periods_snapshot, cliopatria_snapshot, reference_candidates_snapshot,
                               github_reports_snapshot],
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
        for dataset in (MRDS, WIKIDATA, WIKIDATA_ITEMS, PLEIADES, PLEIADES_PERIODS, CLIOPATRIA, REFERENCES, REPORTS):
            snapshot = loaded["upstream"][dataset.name]
            yield MaterializeResult(asset_key=raw[dataset.name], metadata={"rows": snapshot["rows"], "copy": snapshot["copy"]})
        yield MaterializeResult(asset_key=raw["upstream_snapshots"], metadata={"datasets": len(loaded["upstream"])})

    @asset(
        deps=[get_asset_key_for_model([graph_models], name) for name in (
            "graph_nodes", "graph_facts", "source_occurrences", "curation_queue", "reference_checks", "profile_areas",
            "profile_occurrences", "profile_sources")],
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

    @op(description="Agents work through the top of the curation queue for one task: ore crosswalk rows for ore "
        "candidates, or quoted sources for routes whose references are all unverified. Code and a reviewer agent check "
        "each proposal; what passes becomes a draft pull request (ADR 0035, ADR 0048, ADR 0049). Uses Claude Code on "
        "your Claude login, so it draws on your plan's usage limits.")
    def curate(context: OpExecutionContext, config: AgentRunConfig, downloads: UpstreamDownloads) -> dict:
        report = run_agents(
            root, build_dir, Settings(**(config.model_dump() | {"names": tuple(config.names)})),
            Downloads(downloads.wikidata_url, downloads.openalex_url, downloads.crossref_url,
                      downloads.wikidata_site_url),
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

    @job(description="Started by hand only, with a task and a size: agents work through the curation queue (ADR 0048, "
         "ADR 0049).")
    def agent_curation():
        curate()

    @op(description="Checks merged agent facts again, chosen by run, prompt version or model: code's checks (the page "
        "still loads, the quote is still on it), and the reviewer agent if asked, which uses your Claude plan. Changes "
        "no data; what fails is listed, and reported as GitHub issues if asked (ADR 0050).")
    def recheck(context: OpExecutionContext, config: RecheckConfig, downloads: UpstreamDownloads) -> dict:
        fields = config.model_dump()
        settings = RecheckSettings(**(fields | {name: tuple(fields[name]) for name in ("runs", "prompt_versions", "models")}))
        summary = recheck_facts(root, settings, Downloads(downloads.wikidata_url, downloads.openalex_url,
                                                          downloads.crossref_url, downloads.wikidata_site_url),
                                on_progress=context.log.info)
        context.add_output_metadata({"recheck": summary["recheck"], "outcomes": summary["outcomes"],
                                     "not_rechecked": summary["not_rechecked"],
                                     "stopped_because": summary["stopped_because"] or ""})
        return summary

    @job(description="Started by hand only, by an admin: checks merged agent facts again (ADR 0050). Nothing in the app "
         "starts it.")
    def agent_recheck():
        recheck()

    return Definitions(
        assets=[mrds_snapshot, wikidata_snapshot, wikidata_items_snapshot, pleiades_snapshot, pleiades_periods_snapshot,
                cliopatria_snapshot, reference_candidates_snapshot, github_reports_snapshot, raw_tables, graph_models,
                graph_manifest],
        jobs=[agent_curation, agent_recheck],
        resources={"dbt": DbtCliResource(project_dir=project), "downloads": UpstreamDownloads()},
    )
