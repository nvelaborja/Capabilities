import json
from pathlib import Path

import duckdb
import pytest

from capabilities.built import FACTS_FILE, graph_dir, load_built
from capabilities_pipeline.build import build
from capabilities_pipeline.upstream import WIKIDATA, crosswalked_items, fetch, quantities_query, quantity_properties


def facts(build_dir: Path) -> dict[str, dict]:
    relation = duckdb.sql(
        "select id, layer, value::varchar, curated_value::varchar, upstream_value::varchar, disagrees, "
        "upstream::varchar, override::varchar from read_parquet(?) where id is not null",
        params=[str(graph_dir(build_dir) / FACTS_FILE)],
    )
    rows = {}
    for row in relation.fetchall():
        fact = dict(zip(("id", "layer", "value", "curated_value", "upstream_value", "disagrees", "upstream", "override"), row))
        for key in ("value", "curated_value", "upstream_value", "upstream", "override"):
            fact[key] = json.loads(fact[key]) if fact[key] is not None else None
        rows[fact["id"]] = fact
    return rows


def hardness(build_dir: Path, thing: str) -> dict:
    return facts(build_dir)[f"{thing}/quantities.hardness_mohs"]


def build_with_wikidata(root: Path, build_dir: Path, endpoint) -> Path:
    fetch(WIKIDATA, build_dir, endpoint.url, root=root)
    build(root, build_dir)
    return build_dir


class TestTheQuery:
    def test_asks_for_every_crosswalked_item_and_every_quantity_with_a_wikidata_property(self, repo_root):
        items, properties = crosswalked_items(repo_root), quantity_properties(repo_root)
        assert {"Q41177", "Q103223"} <= set(items)
        assert properties == {"P1088": "hardness_mohs"}
        query = quantities_query(items, properties)
        assert "wd:Q41177" in query and "p:P1088" in query
        # Only what Wikidata treats as current: a deprecated statement isn't a value.
        assert "wikibase:BestRank" in query

    def test_there_is_nothing_to_ask_without_items_or_properties(self):
        with pytest.raises(ValueError, match="Nothing to ask Wikidata"):
            quantities_query([], {"P1088": "hardness_mohs"})


class TestTheSnapshot:
    def test_records_the_query_its_license_and_the_result_as_published(self, repo_root, tmp_path, wikidata_endpoint):
        snapshot = fetch(WIKIDATA, tmp_path, wikidata_endpoint.url, root=repo_root)
        assert snapshot["query"] == wikidata_endpoint.queries[-1]
        assert snapshot["rows"] == 4
        assert snapshot["license"].startswith("CC0")
        relation = duckdb.sql("select * from read_parquet(?)", params=[str(WIKIDATA.parquet(tmp_path))])
        assert tuple(relation.columns) == WIKIDATA.columns
        # Kept as text: "6.0" stays "6.0", and a missing bound stays missing.
        assert ("Q41177", "6.0", "5.0", "7.0") in relation.select("item, amount, lower, upper").fetchall()
        assert ("Q753", "3.0", None, None) in relation.select("item, amount, lower, upper").fetchall()


@pytest.fixture(scope="module")
def wikidata_build(repo_root, tmp_path_factory, wikidata_endpoint) -> Path:
    return build_with_wikidata(repo_root, tmp_path_factory.mktemp("build"), wikidata_endpoint)


class TestChoosingAValue:
    def test_an_upstream_value_is_used_over_the_curated_one(self, repo_root, wikidata_build):
        granite = hardness(wikidata_build, "granite")
        assert (granite["layer"], granite["value"]) == ("upstream", [5, 7])
        assert load_built(repo_root, wikidata_build).things["granite"]["quantities"]["hardness_mohs"] == [5, 7]

    def test_says_which_record_it_came_from_and_when_it_was_retrieved(self, wikidata_build):
        upstream = hardness(wikidata_build, "granite")["upstream"]
        assert upstream["dataset"] == "wikidata"
        assert upstream["record"] == "Q41177"
        assert upstream["url"] == "https://www.wikidata.org/wiki/Q41177"
        assert upstream["retrieved_at"].endswith("Z")

    def test_a_curated_value_that_disagrees_is_kept_beside_it(self, wikidata_build):
        granite, hematite = hardness(wikidata_build, "granite"), hardness(wikidata_build, "hematite")
        assert (granite["curated_value"], granite["disagrees"]) == ([6, 7], True)
        assert (hematite["curated_value"], hematite["disagrees"]) == ([5.5, 6.5], False)

    def test_a_statement_without_bounds_is_a_single_value(self, wikidata_build):
        assert hardness(wikidata_build, "copper")["value"] == 3

    def test_a_thing_wikidata_has_no_value_for_keeps_its_curated_one(self, wikidata_build):
        flint = hardness(wikidata_build, "flint")
        assert (flint["layer"], flint["value"], flint["upstream"]) == ("curated", [6.5, 7], None)

    def test_without_a_snapshot_every_value_is_curated(self, built_dir):
        assert {fact["layer"] for fact in facts(built_dir).values()} == {"curated"}


class TestOverridesAndSuppressions:
    def test_an_override_replaces_the_upstream_value_and_says_why(self, data_copy, tmp_path, wikidata_endpoint, write_override):
        write_override(data_copy)
        granite = hardness(build_with_wikidata(data_copy, tmp_path / "build", wikidata_endpoint), "granite")
        assert (granite["layer"], granite["value"], granite["upstream_value"]) == ("override", [6, 7], [5, 7])
        override = granite["override"]
        assert override["reason"].startswith("Granite's common minerals")
        assert override["references"][0]["citation"].startswith("Klein")
        assert (override["replaces"], override["stale"]) == ([5, 7], False)

    def test_an_override_of_a_value_upstream_has_since_changed_is_flagged(
        self, data_copy, tmp_path, wikidata_endpoint, write_override
    ):
        write_override(data_copy, replaces="[4, 7]")
        granite = hardness(build_with_wikidata(data_copy, tmp_path / "build", wikidata_endpoint), "granite")
        assert (granite["value"], granite["override"]["stale"]) == ([6, 7], True)

    def test_a_suppressed_record_is_left_out(self, data_copy, tmp_path, wikidata_endpoint):
        suppressions = data_copy / "data" / "suppressions" / "suppressed_records.csv"
        suppressions.write_text(
            suppressions.read_text() + 'wikidata,Q41177,"Test: the item describes granite in general."\n', encoding="utf-8"
        )
        granite = hardness(build_with_wikidata(data_copy, tmp_path / "build", wikidata_endpoint), "granite")
        assert (granite["layer"], granite["value"]) == ("curated", [6, 7])

    def test_an_override_of_a_value_only_the_curated_layer_gives_fails_the_build(
        self, data_copy, tmp_path, wikidata_endpoint, write_override
    ):
        from capabilities_pipeline.build import BuildError

        # Quartz sand has no Wikidata item: change its curated value instead.
        write_override(data_copy, id="quartz-sand-hardness", thing="quartz-sand")
        with pytest.raises(BuildError, match="overrides_target_upstream_values"):
            build_with_wikidata(data_copy, tmp_path / "build", wikidata_endpoint)
