"""Readers' reports (ADR 0050): GitHub issues from the app's "Report a problem" link, read by Dagster and queued first.
The issues are a recording (fixtures/github-report-issues.json), served by a stand-in for GitHub's API."""

import duckdb
import pytest

from capabilities.built import load_queue
from capabilities_pipeline.upstream import REPORTS, fetch, report_fields


class TestReadingReports:
    def test_the_fields_the_app_filled_in_are_read_from_the_issue_and_empty_ones_left_out(self):
        body = ("### Fact\n\nsmelt-copper\n\n### Kind\n\nroute\n\n### Reference\n\n_No response_\n\n"
                "### Agent run\n\n_No response_\n\n### What is wrong\n\nIt needs more heat.\n\n### A better source\n\nNone")
        assert report_fields(body) == {"fact": "smelt-copper", "kind": "route"}

    def test_a_heading_the_reader_types_doesnt_replace_a_field_the_app_filled_in(self):
        body = ("### Fact\n\nsmelt-copper\n\n### Kind\n\nroute\n\n### What is wrong\n\nSee below.\n\n"
                "### Fact\n\nsmelt-tin\n\n### A better source\n\n_No response_")
        assert report_fields(body) == {"fact": "smelt-copper", "kind": "route"}

    def test_what_the_reporter_wrote_and_who_they_are_are_left_on_github(self, tmp_path, github_endpoint):
        fetch(REPORTS, tmp_path, github_endpoint.url)
        columns = duckdb.sql("select * from read_parquet(?)", params=[str(REPORTS.parquet(tmp_path))]).columns
        assert columns == list(REPORTS.columns)
        assert not {"user", "body", "problem", "source"} & set(columns)

    def test_open_reports_are_kept_and_pull_requests_left_out(self, tmp_path, github_endpoint):
        snapshot = fetch(REPORTS, tmp_path, github_endpoint.url)
        rows = duckdb.sql("select number, fact, kind, run from read_parquet(?) order by cast(number as int)",
                          params=[str(REPORTS.parquet(tmp_path))]).fetchall()
        # (an empty field reads back as null)
        assert rows == [("7", "twist-test-cord", "reference", "routes-20260101-120000"),
                        ("9", "twist-test-cord", "route", None), ("11", None, None, None)]
        assert snapshot["rows"] == 3
        assert "labels=report" in github_endpoint.requests[-1] and "state=open" in github_endpoint.requests[-1]


@pytest.fixture(scope="module")
def reported(upstream_built_dir):
    queue = load_queue(upstream_built_dir)
    return queue, [item for item in queue if item["kind"] == "reported"]


class TestTheQueue:
    def test_reports_come_first(self, reported):
        queue, items = reported
        assert queue[: len(items)] == items

    def test_reports_of_one_fact_are_one_item_listing_each_issue(self, reported):
        _, items = reported
        twist = next(item for item in items if item["subject"] == "twist-test-cord")
        assert twist["priority"] == 2
        assert twist["detail"].startswith("Reported in #7 (Report: the quote is about another site), #9 (")
        assert "capabilities withdraw" in twist["detail"]

    def test_a_report_naming_no_fact_is_still_an_item_to_read(self, reported):
        _, items = reported
        assert [(item["subject"], item["label"]) for item in items if item["subject"].startswith("#")] == [
            ("#11", "Report: something about copper")]
