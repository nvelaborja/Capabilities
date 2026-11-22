"""The build as Dagster assets: the curated load, every dbt model (its data tests become asset checks), and the manifest.

`capabilities build` runs the same steps without Dagster (build.py). definitions.py is what Dagster loads.
"""

# No `from __future__ import annotations`: Dagster inspects the `context` annotation at definition time.
from pathlib import Path

from capabilities.built import NODES_FILE, graph_dir
from dagster import AssetExecutionContext, Definitions, MaterializeResult, asset
from dagster_dbt import (
    DagsterDbtTranslator,
    DagsterDbtTranslatorSettings,
    DbtCliResource,
    DbtProject,
    dbt_assets,
    get_asset_key_for_model,
    get_asset_key_for_source,
)

from .build import DBT_PROJECT, dbt_environment, dbt_target_path, load_curated, write_manifest


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

    # The dbt source raw.curated_documents is this asset, so the lineage runs from the YAML through every model.
    @asset(
        key=get_asset_key_for_source([graph_models], "raw"),
        group_name="raw",
        description="Every curated YAML document, whole, loaded into DuckDB with the fingerprint of the inputs.",
    )
    def curated_documents() -> MaterializeResult:
        return MaterializeResult(metadata={"documents": load_curated(root, build_dir)})

    @asset(
        deps=[get_asset_key_for_model([graph_models], "graph_nodes")],
        group_name="marts",
        description="graph/manifest.json: what the built graph was made from. The app reads only a build whose "
        "manifest matches its inputs (ADR 0038).",
    )
    def graph_manifest() -> MaterializeResult:
        manifest = write_manifest(root, build_dir)
        return MaterializeResult(
            metadata={
                "nodes": manifest["tables"][NODES_FILE],
                "fingerprint": manifest["fingerprint"],
                "path": str(graph_dir(build_dir)),
            }
        )

    return Definitions(
        assets=[curated_documents, graph_models, graph_manifest],
        resources={"dbt": DbtCliResource(project_dir=project)},
    )
