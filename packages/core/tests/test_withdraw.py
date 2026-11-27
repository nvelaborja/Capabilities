"""Withdrawing agents' facts (ADR 0050). Every route, row and run here is made up and written into a copy of the data, so
nothing depends on what an agent's pull request has merged."""

import csv
import json
from datetime import date

import pytest
import yaml

from capabilities.cli import main
from capabilities.validate import validate
from capabilities.withdraw import WithdrawError, withdraw_ore_row, withdraw_reference, withdrawals

RUN = "routes-20260101-120000"
ORE_RUN = "ore-20260101-120000"
PERSON = "Weaver, A. (1990). Cordage of the ancients. Example Press."
AGENTS = "Braider, C. (2019). Plant fiber rope at an example site. Example Journal."
QUOTE = "Ropes were twisted from plant fibers by hand in the Bronze Age."
ROUTE = f"""id: twist-test-cord
kind: route
label: Twisting test cord
achieves: {{ thing: rope }}
requires:
  - {{ role: consumed, thing: plant-fiber }}
outputs:
  - {{ thing: rope }}
references:
  # A person's reference, which an agent quoted.
  - citation: "{PERSON}"
    supports: Rope was twisted from plant fibres.
    url: "https://example.org/cordage.pdf"
    quote: "{QUOTE}"
    status: unverified
    proposed_by: {RUN}
  - citation: "{AGENTS}"
    url: "https://example.org/rope"
    supports: "Rope was made from plant fibers."
    quote: "Rope was braided from plant fibers by hand."
    status: unverified
    proposed_by: {RUN}
  - citation: "Spinner, B. (2001). Cord at an example site. Example Journal."
    supports: Rope was twisted at the site.
    status: unverified
"""
# What the run's pull request committed: it quoted the person's reference, giving it its URL, and added the other.
SUMMARY = {"run": RUN, "items": [
    {"item": "twist-test-cord", "outcome": "accepted", "change": {
        "route": "twist-test-cord", "reference": 0, "citation": PERSON, "adds_url": True}},
]}
ADDED = {"item": "twist-test-cord", "outcome": "accepted", "change": {
    "route": "twist-test-cord", "reference": None, "citation": AGENTS}}
ORE_QUOTE = "Galena was not smelted for copper at the site."
DAY = date(2026, 1, 2)


@pytest.fixture
def cord(data_copy):
    (data_copy / "data" / "routes" / "twist-test-cord.yaml").write_text(ROUTE, encoding="utf-8")
    runs = data_copy / "data" / "agent_runs"
    runs.mkdir(exist_ok=True)
    summary = dict(SUMMARY, items=SUMMARY["items"] + [ADDED])
    (runs / f"{RUN}.json").write_text(json.dumps(summary), encoding="utf-8")
    return data_copy


def _route(root) -> dict:
    return yaml.safe_load((root / "data" / "routes" / "twist-test-cord.yaml").read_text(encoding="utf-8"))


def _with_agents_ore_row(root, mineral="Testite", mined_like="") -> None:
    path = root / "data" / "crosswalks" / "ore_minerals.csv"
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        columns, rows = reader.fieldnames, list(reader)
    rows.append({column: "" for column in columns} | {
        "mrds_ore": mineral, "class": "none", "citation": AGENTS, "mined_like": mined_like,
        "id": mineral.lower() if mined_like else "", "url": "https://example.org/rope",
        "supports": "Not smelted for copper.", "quote": ORE_QUOTE, "proposed_by": ORE_RUN})
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


class TestWithdrawingARoutesReference:
    def test_a_reference_an_agent_added_is_removed_whole(self, cord):
        before = (cord / "data" / "routes" / "twist-test-cord.yaml").read_text(encoding="utf-8")
        withdrawal = withdraw_reference(cord, "twist-test-cord", AGENTS, "The page is about modern rope.", "12", DAY)
        assert [r["citation"] for r in _route(cord)["references"]] == [PERSON, "Spinner, B. (2001). Cord at an example "
                                                                       "site. Example Journal."]
        # then: only its lines went; the person's comment and references are as they were
        after = (cord / "data" / "routes" / "twist-test-cord.yaml").read_text(encoding="utf-8")
        assert [line for line in before.splitlines() if line not in after.splitlines()] == [
            f'  - citation: "{AGENTS}"', '    url: "https://example.org/rope"',
            '    supports: "Rope was made from plant fibers."', '    quote: "Rope was braided from plant fibers by hand."']
        assert (withdrawal.kind, withdrawal.run, withdrawal.report) == ("reference", RUN, "12")

    def test_a_quote_on_a_persons_reference_goes_with_the_url_it_brought_and_the_reference_stays(self, cord):
        withdraw_reference(cord, "twist-test-cord", PERSON, "The quote is about another site.", on=DAY)
        assert _route(cord)["references"][0] == {"citation": PERSON, "supports": "Rope was twisted from plant fibres.",
                                                 "status": "unverified"}
        assert "# A person's reference, which an agent quoted." in (
            cord / "data" / "routes" / "twist-test-cord.yaml").read_text(encoding="utf-8")

    def test_the_withdrawal_is_recorded_with_what_the_fact_said(self, cord):
        withdraw_reference(cord, "twist-test-cord", PERSON, "The quote is about another site.", on=DAY)
        assert withdrawals(cord) == [{
            "withdrawn_on": "2026-01-02", "kind": "quote", "subject": "twist-test-cord", "citation": PERSON,
            "url": "https://example.org/cordage.pdf", "quote": QUOTE, "run": RUN,
            "reason": "The quote is about another site.", "report": ""}]

    @pytest.mark.parametrize("route, citation, refused", [
        pytest.param("twist-test-cord", "Spinner, B. (2001). Cord at an example site. Example Journal.",
                     "wasn't proposed by an agent", id="a person's reference"),
        pytest.param("twist-test-cord", "Nobody (2000). Nothing.", "no references cite", id="a citation not there"),
        pytest.param("no-such-route", PERSON, "no route", id="a route not there"),
    ])
    def test_what_no_agent_proposed_is_refused_and_nothing_changes(self, cord, route, citation, refused):
        before = (cord / "data" / "routes" / "twist-test-cord.yaml").read_text(encoding="utf-8")
        with pytest.raises(WithdrawError, match=refused):
            withdraw_reference(cord, route, citation, "Wrong.")
        assert (cord / "data" / "routes" / "twist-test-cord.yaml").read_text(encoding="utf-8") == before
        assert withdrawals(cord) == []

    def test_a_routes_only_reference_is_refused_since_every_route_cites_one(self, cord):
        path = cord / "data" / "routes" / "twist-test-cord.yaml"
        route = _route(cord)
        route["references"] = [route["references"][1]]
        path.write_text(yaml.safe_dump(route, sort_keys=False), encoding="utf-8")
        before = path.read_text(encoding="utf-8")
        with pytest.raises(WithdrawError, match="its only one.*add another reference"):
            withdraw_reference(cord, "twist-test-cord", AGENTS, "Wrong.")
        assert path.read_text(encoding="utf-8") == before and withdrawals(cord) == []

    def test_a_reference_that_cant_be_edited_as_text_is_refused_with_what_to_do(self, cord):
        # given: the person's quoted reference written as one flow mapping, which the editor won't rewrite
        path = cord / "data" / "routes" / "twist-test-cord.yaml"
        route = _route(cord)
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        start = lines.index(f'  - citation: "{PERSON}"\n')
        flow = "  - " + json.dumps(route["references"][0]) + "\n"
        path.write_text("".join(lines[:start] + [flow] + lines[start + 6:]), encoding="utf-8")
        assert _route(cord) == route
        with pytest.raises(WithdrawError, match="edit the file by hand"):
            withdraw_reference(cord, "twist-test-cord", PERSON, "Wrong.")
        assert withdrawals(cord) == []

    def test_a_copied_mining_route_is_withdrawn_from_the_route_it_was_copied_from(self, cord, capsys):
        _with_agents_ore_row(cord, mined_like="twist-test-cord")
        assert main(["--root", str(cord), "withdraw", "reference", "mine-testite", "--citation", AGENTS,
                     "--reason", "Wrong."]) == 0
        assert AGENTS not in [r["citation"] for r in _route(cord)["references"]]
        assert withdrawals(cord)[0]["subject"] == "twist-test-cord"
        assert "mine-testite is copied from twist-test-cord" in capsys.readouterr().out

    def test_without_the_runs_summary_it_cant_tell_what_to_remove(self, cord):
        (cord / "data" / "agent_runs" / f"{RUN}.json").unlink()
        with pytest.raises(WithdrawError, match="summary isn't in"):
            withdraw_reference(cord, "twist-test-cord", AGENTS, "Wrong.")


class TestWithdrawingAnOreRow:
    def test_an_agents_row_is_removed_and_the_rest_of_the_crosswalk_is_untouched(self, data_copy):
        path = data_copy / "data" / "crosswalks" / "ore_minerals.csv"
        original = path.read_text(encoding="utf-8")
        _with_agents_ore_row(data_copy)
        withdrawal = withdraw_ore_row(data_copy, "testite", "Wrong class.", on=DAY)
        assert path.read_text(encoding="utf-8") == original
        assert (withdrawal.kind, withdrawal.subject, withdrawal.quote) == ("ore_row", "Testite", ORE_QUOTE)

    def test_a_persons_row_is_refused(self, data_copy):
        path = data_copy / "data" / "crosswalks" / "ore_minerals.csv"
        before = path.read_text(encoding="utf-8")
        person = next(row for row in csv.DictReader(before.splitlines()) if not row["proposed_by"])
        with pytest.raises(WithdrawError, match="wasn't proposed by an agent"):
            withdraw_ore_row(data_copy, person["mrds_ore"], "Wrong.")
        assert path.read_text(encoding="utf-8") == before


class TestAWithdrawnFactComingBack:
    def test_validate_refuses_a_withdrawn_quote_put_back_on_its_route(self, cord):
        before = (cord / "data" / "routes" / "twist-test-cord.yaml").read_text(encoding="utf-8")
        withdraw_reference(cord, "twist-test-cord", AGENTS, "Wrong.", on=DAY)
        assert not _errors(cord)
        (cord / "data" / "routes" / "twist-test-cord.yaml").write_text(before, encoding="utf-8")
        assert any("was withdrawn" in message for message in _errors(cord))

    def test_validate_refuses_a_withdrawn_ore_row_put_back(self, data_copy):
        _with_agents_ore_row(data_copy)
        withdraw_ore_row(data_copy, "Testite", "Wrong.", on=DAY)
        _with_agents_ore_row(data_copy)
        assert any("Testite: this quote was withdrawn" in message for message in _errors(data_copy))


class TestTheCommand:
    def test_withdraw_reference_says_what_it_did_and_what_to_do_next(self, cord, capsys):
        assert main(["--root", str(cord), "withdraw", "reference", "twist-test-cord", "--citation", AGENTS,
                     "--reason", "Wrong.", "--report", "12"]) == 0
        out = capsys.readouterr().out
        assert f"the reference an agent added to twist-test-cord (run {RUN})" in out and "Closes #12" in out

    def test_a_refusal_is_an_error_not_a_traceback(self, cord, capsys):
        assert main(["--root", str(cord), "withdraw", "ore", "No such mineral", "--reason", "Wrong."]) == 2
        assert "has no row for" in capsys.readouterr().err


def _errors(root) -> list[str]:
    return [f"{i.where}: {i.message}" for i in validate(root) if i.severity == "error"]

