"""Agents proposing ore crosswalk rows (ADR 0035, ADR 0048).

No test uses Claude, the web or GitHub: `claude` and `gh` are local stand-ins (fixtures/agents), pages and Wikidata
items come from a fake web, and the gate's downloads go to the local Wikidata, OpenAlex and Crossref stand-ins
(conftest). The minerals, items, pages and sources here are made up for the tests unless a comment says otherwise.
"""

import csv
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import duckdb
import pytest
import yaml

from capabilities_pipeline.agents import claude as claude_module
from capabilities_pipeline.agents.audit import AUDIT_FILE
from capabilities_pipeline.agents.branch import Downloads, Worktree
from capabilities_pipeline.agents.claude import (
    AgentError,
    ClaudeCode,
    NotOnClaudeLogin,
    UsageLimitReached,
    check_login,
    parse,
)
from capabilities_pipeline.agents.curate import Settings
from capabilities_pipeline.agents import task as task_module
from capabilities_pipeline.agents.ore_candidates import (
    ORE_CLASSES,
    Candidate,
    Context,
    OreCandidates,
    Proposal,
    check,
    evaluation_set,
    score,
    write_crosswalk,
)
from capabilities_pipeline.agents.run import pull_request_body, run_agents
from capabilities_pipeline.agents.sources import Library, Source, Wanted, known_sources, openalex_citation
from capabilities_pipeline.agents.task import Prompt
from capabilities_pipeline.agents.web import (
    MINERAL_SPECIES,
    Page,
    Web,
    WikidataItem,
    html_text,
    locate,
    not_public,
    read,
)

FAKE_CLAUDE = Path(__file__).parent / "fixtures" / "agents" / "fake_claude.py"
COVELLITE = Candidate("Covellite", "Listed as an ore mineral on 816 MRDS deposits of copper, iron, tin.")
COVELLITE_ITEM = WikidataItem("Q99999901", "covellite", "copper sulfide mineral", ("indigo copper",))
PAGE_URL = "https://example.org/sulphide-ores"
QUOTE = "Covellite and chalcocite were roasted with the other copper sulphides before smelting."
PAGE = Page(PAGE_URL, "200", "Sulphide ores\nAt the site, " + QUOTE + " The slag shows it.", "Sulphide ores", "html")
CITATION = "Example, A. (2020). Sulphide ores at an example site. Example Journal 1, 1–10."
# A proposal as code makes it from the proposer's choice, for the mechanical checks.
PROPOSED = {"wikidata": "Q99999901", "class": "copper-sulphide-ore", "citation": CITATION, "url": PAGE_URL,
            "quote": QUOTE, "supports": "Covellite was roasted and smelted for copper.", "notes": "A copper sulphide."}
# The top of the repository's queue, Galena, and the made-up page and OpenAlex work a run finds for it.
GALENA_ITEM = WikidataItem("Q99999910", "galena", "lead sulfide mineral")
GALENA_URL = "https://example.org/galena.pdf"
GALENA_SENTENCE = "Galena was roasted with the other sulphides before smelting it for silver."
GALENA_PAGE = Page(GALENA_URL, "200", "Notes on ores. " + GALENA_SENTENCE + " More notes.", None, "pdf")
GALENA_WORK = {"id": "W1", "display_name": "Lead ores at an example site", "publication_year": 2021,
               "authorships": [{"author": {"display_name": "Ada Example"}}],
               "primary_location": {"source": {"display_name": "Example Journal"}},
               "best_oa_location": {"pdf_url": GALENA_URL}}
# The queue's second item, Sphalerite, for runs of more than one item.
SPHALERITE_ITEM = WikidataItem("Q99999911", "sphalerite", "zinc sulfide mineral")
SPHALERITE_URL = "https://example.org/sphalerite.pdf"
SPHALERITE_PAGE = Page(SPHALERITE_URL, "200", "Sphalerite was roasted with the copper sulphides at the example mine.",
                       None, "pdf")
SPHALERITE_WORK = GALENA_WORK | {"id": "W4", "best_oa_location": {"pdf_url": SPHALERITE_URL}}
# The proposer's choice: a class and passage 1, which is the Galena sentence when nothing else is found.
GOOD = {"decision": "propose", "class": "copper-sulphide-ore", "passage": 1,
        "supports": "Galena was roasted before smelting.", "notes": "A lead sulphide.", "unsure_why": ""}
UNSURE = {"decision": "unsure", "class": "", "passage": 0, "supports": "", "notes": "", "unsure_why": "No source says."}
ACCEPT = {"verdict": "accept", "objections": [], "summary": "The quote supports the class."}


def proposed(**changes) -> Proposal:
    fields = PROPOSED | changes
    return Proposal("propose", fields["wikidata"], fields["class"], fields["citation"], fields["url"], fields["quote"],
                    fields["supports"], fields["notes"])


class FakeWeb:
    """Pages, Wikidata items and OpenAlex works, by URL, id and mineral; anything else isn't there. Every item is a
    mineral species unless it says otherwise."""

    def __init__(self, pages=None, items=None, works=None):
        self.pages = {PAGE_URL: PAGE, GALENA_URL: GALENA_PAGE, SPHALERITE_URL: SPHALERITE_PAGE, **(pages or {})}
        items = {COVELLITE_ITEM.id: COVELLITE_ITEM, GALENA_ITEM.id: GALENA_ITEM, SPHALERITE_ITEM.id: SPHALERITE_ITEM,
                 **(items or {})}
        self.items = {key: item if item is None or item.instance_of else replace(item, instance_of=(MINERAL_SPECIES,))
                      for key, item in items.items()}
        self.works = {"galena": [GALENA_WORK], "sphalerite": [SPHALERITE_WORK], **(works or {})}
        self.asked: list[str] = []
        self.searched: list[str] = []
        self.items_asked: list[str] = []

    def page(self, url: str) -> Page:
        self.asked.append(url)
        return self.pages.get(url, Page(url, "404"))

    def wikidata_item(self, item: str) -> WikidataItem | None:
        self.items_asked.append(item)
        return self.items.get(item)

    def wikidata_search(self, name: str) -> list[str]:
        return [key for key, item in self.items.items() if item and item.is_called(name)]

    def openalex_works(self, search: str, count: int) -> list[dict]:
        self.searched.append(search)
        return self.works.get(search.split()[0].lower(), [])[:count]


class FakeClaude:
    """The `claude` stand-in, installed as an executable, with a script of answers and a log of calls."""

    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.command = directory / "claude"
        self.command.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE_CLAUDE}" "$@"\n')
        self.command.chmod(self.command.stat().st_mode | stat.S_IEXEC)
        self.log, self.script_file = directory / "calls.jsonl", directory / "script.json"

    def script(self, proposer=(), reviewer=()) -> None:
        self.script_file.write_text(json.dumps({"proposer": list(proposer), "reviewer": list(reviewer)}))
        Path(str(self.script_file) + ".state").unlink(missing_ok=True)
        self.log.unlink(missing_ok=True)

    def calls(self, role: str | None = None) -> list[dict]:
        if not self.log.exists():
            return []
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        return [call for call in calls if role in (None, call["role"])]

    def environment(self) -> dict[str, str]:
        return {"FAKE_CLAUDE_LOG": str(self.log), "FAKE_CLAUDE_SCRIPT": str(self.script_file)}


@pytest.fixture
def fake_claude(tmp_path, monkeypatch) -> FakeClaude:
    fake = FakeClaude(tmp_path / "fake-claude")
    for name, value in fake.environment().items():
        monkeypatch.setenv(name, value)
    for name in claude_module.API_CREDENTIALS:
        monkeypatch.delenv(name, raising=False)
    return fake


@pytest.fixture(scope="module")
def context(repo_root) -> Context:
    return Context.of(repo_root)


def answer(output: dict, **extra) -> dict:
    return {"output": output, **extra}


def settings(fake: FakeClaude, **changes) -> Settings:
    return Settings(claude_command=str(fake.command), pull_request=False, **changes)


# The minerals the test runs name, in order, so no test depends on what the repository's queue holds: a pull request that
# decides Galena moves the queue on (PR #24, 2026-11-25). Gold has no item in the fake web, so it is skipped.
MINERALS = ("Galena", "Sphalerite", "Gold", "Chrysocolla", "Limonite")


def run(root, build_dir, fake, web=None, audit_dir=None, **changes):
    changes.setdefault("names", MINERALS)
    return run_agents(root, build_dir, settings(fake, **changes), web=web or FakeWeb(),
                      on_progress=lambda message: None, audit_dir=audit_dir)


def galena_passages(library: Library):
    """The passages a run finds for Galena (OreCandidates.find, without the item lookup)."""
    return library.passages(Wanted.mineral({"Galena", GALENA_ITEM.label}),
                            ["Galena archaeometallurgy", "Galena ancient smelting"])


def audit_rows(audit_dir: Path, query: str) -> list[tuple]:
    with duckdb.connect(str(audit_dir / AUDIT_FILE), read_only=True) as connection:
        return connection.execute(query).fetchall()


class TestCallingClaudeCode:
    def test_a_call_runs_on_the_login_with_only_its_tools_and_no_saved_session(self, fake_claude):
        fake_claude.script(proposer=[answer({"word": "ok"})])
        ClaudeCode("opus", ("WebSearch", "WebFetch"), 30, str(fake_claude.command)).ask("The task.", "The role.", {})
        call = fake_claude.calls()[0]
        argv = call["argv"]
        # given no API key (the fixture removed any): Claude Code uses the login
        assert not call["api_key"]
        assert {"-p", "--safe-mode", "--strict-mcp-config", "--no-session-persistence"} <= set(argv)
        assert argv[argv.index("--tools") + 1] == "WebSearch,WebFetch"
        assert argv[argv.index("--allowedTools") + 1] == "WebSearch,WebFetch"
        assert argv[argv.index("--max-turns") + 1] == "30"
        # the prompt goes in on stdin, where no option can swallow it
        assert call["prompt"] == "The task." and "The task." not in argv

    def test_a_reviewer_gets_no_tools(self, fake_claude):
        fake_claude.script(reviewer=[answer(ACCEPT)])
        ClaudeCode("opus", (), 3, str(fake_claude.command)).ask("Review.", "You review.", {})
        argv = fake_claude.calls()[0]["argv"]
        assert argv[argv.index("--tools") + 1] == "" and "--allowedTools" not in argv

    def test_an_answer_carries_its_tools_usage_and_the_plans_usage(self, fake_claude):
        fake_claude.script(proposer=[answer({"x": 1}, searches=["covellite ore"], fetches=[PAGE_URL], five_hour=0.5)])
        result = ClaudeCode("opus", ("WebSearch",), 30, str(fake_claude.command)).ask("Task.", "Role.", {})
        assert result.output == {"x": 1}
        assert result.tool_calls == [{"name": "WebSearch", "input": {"query": "covellite ore"}},
                                     {"name": "WebFetch", "input": {"url": PAGE_URL, "prompt": "Quote it."}}]
        assert result.limits == {"five_hour": 0.5, "seven_day": 0.1}
        assert result.cost_usd == 0.25 and result.usage["output_tokens"] == 100
        # the role asked for an alias; the answer says which model that meant
        assert result.model == "claude-opus-5-5"

    @pytest.mark.parametrize("scripted, error", [
        pytest.param({"limit": True}, UsageLimitReached, id="the plan's limit is reached"),
        pytest.param({"error": "max_turns"}, AgentError, id="out of turns"),
    ])
    def test_a_call_without_an_answer_says_why(self, fake_claude, scripted, error):
        fake_claude.script(proposer=[scripted])
        with pytest.raises(error):
            ClaudeCode("opus", ("WebSearch",), 30, str(fake_claude.command)).ask("Task.", "Role.", {})

    def test_a_call_that_runs_out_of_turns_still_says_what_it_spent(self, fake_claude):
        fake_claude.script(proposer=[{"error": "max_turns", "five_hour": 0.7}])
        with pytest.raises(AgentError) as raised:
            ClaudeCode("opus", ("WebSearch",), 30, str(fake_claude.command)).ask("Task.", "Role.", {})
        spent = raised.value.spent
        assert spent.limits["five_hour"] == 0.7 and spent.usage["output_tokens"] == 100 and spent.output == {}

    def test_the_effort_asked_for_is_passed_on(self, fake_claude):
        fake_claude.script(proposer=[answer({"x": 1})])
        ClaudeCode("sonnet", ("WebSearch",), 30, str(fake_claude.command), effort="medium").ask("Task.", "Role.", {})
        argv = fake_claude.calls()[0]["argv"]
        assert argv[argv.index("--model") + 1] == "sonnet" and argv[argv.index("--effort") + 1] == "medium"

    def test_a_limit_reached_before_any_result_is_still_a_limit(self):
        with pytest.raises(UsageLimitReached):
            parse("", "Claude AI usage limit reached|1795573200", 1)

    def test_an_answer_with_no_structured_output_is_unusable(self):
        result = {"type": "result", "subtype": "success", "is_error": False, "result": "Done."}
        with pytest.raises(AgentError, match="no structured output"):
            parse(json.dumps(result))

    def test_an_api_key_in_the_environment_stops_everything(self, fake_claude, monkeypatch):
        # given: a key, which Claude Code would use instead of the login, billing it
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        with pytest.raises(NotOnClaudeLogin, match="ANTHROPIC_API_KEY"):
            check_login(str(fake_claude.command))
        with pytest.raises(NotOnClaudeLogin):
            ClaudeCode("opus", (), 3, str(fake_claude.command)).ask("Task.", "Role.", {})
        assert fake_claude.calls() == []

    @pytest.mark.parametrize("status, message", [
        pytest.param({"loggedIn": True, "authMethod": "apiKey"}, "not a Claude login", id="an API key login"),
        pytest.param({"loggedIn": False}, "isn't logged in", id="logged out"),
    ])
    def test_a_run_needs_a_claude_login(self, fake_claude, monkeypatch, status, message):
        monkeypatch.setenv("FAKE_CLAUDE_AUTH", json.dumps(status))
        with pytest.raises(NotOnClaudeLogin, match=message):
            check_login(str(fake_claude.command))

    def test_the_login_check_keeps_the_plan_but_not_the_account(self, fake_claude):
        assert check_login(str(fake_claude.command)) == {"auth": "claude.ai", "plan": "pro"}


class TestReadingWhatIsCited:
    def test_a_pages_text_leaves_out_scripts_and_keeps_its_title(self):
        title, text = html_text("<html><head><title>Ores</title><script>var x;</script></head><body><p>One.</p>"
                                "<style>p{}</style><p>Two &amp; three.</p></body></html>")
        assert (title, text) == ("Ores", "One.\nTwo & three.")

    @pytest.mark.parametrize("quote", [
        pytest.param("COVELLITE AND CHALCOCITE", id="in another case"),
        pytest.param('chalcocite - the "glance" ores - were roasted', id="with straight quotes and hyphens for curly ones"),
        pytest.param("Covellite and chalcocite … were roasted", id="with words left out"),
        pytest.param("the other copper sulphides before smelting", id="across a word a PDF broke"),
    ])
    def test_a_quote_is_found_word_for_word_whatever_its_typography(self, quote):
        text = "Covellite and chalcocite – the “glance” ores – were roasted with the other copper sul-\nphides before smelting."
        assert locate(quote, text) is not None

    @pytest.mark.parametrize("quote", [
        pytest.param("Covellite and chalcocite were smelted", id="a word changed"),
        pytest.param("before smelting … Covellite", id="parts out of order"),
    ])
    def test_a_paraphrase_is_not_found(self, quote):
        assert locate(quote, "Covellite and chalcocite were roasted before smelting.") is None

    def test_a_pdfs_text_is_read(self):
        page = read(PAGE_URL, "200", _pdf("Covellite was roasted before smelting."), "application/pdf", "utf-8")
        assert page.kind == "pdf" and "Covellite was roasted before smelting." in page.text

    def test_a_file_that_isnt_a_page_isnt_read(self):
        assert read(PAGE_URL, "200", b"\x00\x01", "image/png", "utf-8").status == "not a page we can read (image/png)"


def _pdf(text: str) -> bytes:
    """A one-page PDF with one line of text in Helvetica."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


class TestMechanicalChecks:
    def test_a_good_proposal_passes_every_check_and_the_reviewer_reads_the_page_around_the_quote(self, context):
        checks, evidence = check(COVELLITE, proposed(), context, FakeWeb())
        assert [c.name for c in checks if not c.passed] == []
        assert QUOTE in evidence.excerpt and evidence.item.id == COVELLITE_ITEM.id

    @pytest.mark.parametrize("change, failed", [
        pytest.param({"class": "tin-ore"}, "class_is_known", id="a class no row has shown how to mine yet"),
        pytest.param({"wikidata": "Q99999902"}, "wikidata_item_is_the_mineral", id="an item that isn't the mineral"),
        pytest.param({"wikidata": "Q404"}, "wikidata_item_is_the_mineral", id="no such item"),
        pytest.param({"wikidata": "Q99999903"}, "wikidata_item_is_the_mineral", id="an item merged into another"),
        pytest.param({"wikidata": "Q108212"}, "wikidata_item_is_new", id="an item already in the crosswalk"),
        pytest.param({"url": "https://www.mindat.org/min-1144.html"}, "source_may_be_used", id="Mindat"),
        pytest.param({"url": "https://example.org/gone"}, "cited_page_loads", id="a page that doesn't load"),
        pytest.param({"quote": QUOTE.replace("roasted", "heated")}, "quote_is_on_the_page", id="a paraphrase"),
        pytest.param({"quote": "Covellite was roasted."}, "quote_is_on_the_page", id="a quote too short"),
        pytest.param({"quote": "At the site, the slag shows it."}, "quote_names_the_mineral",
                     id="a quote that doesn't name the mineral"),
    ])
    def test_a_proposal_that_fails_a_check_says_which(self, context, change, failed):
        web = FakeWeb(pages={"https://example.org/gone": Page("https://example.org/gone", "404")}, items={
            "Q99999902": WikidataItem("Q99999902", "chalcocite", "copper sulfide mineral"),
            "Q99999903": WikidataItem("Q99999901", "covellite", None),  # merged: the answer is keyed by its new id
            "Q108212": WikidataItem("Q108212", "covellite", None),  # azurite's item, as if it were covellite's
        })
        page = Page(PAGE_URL, "200", "At the site, the slag shows it. " + PAGE.text, "Sulphide ores", "html")
        web.pages[PAGE_URL] = page
        checks, _ = check(COVELLITE, proposed(**change), context, web)
        assert failed in [c.name for c in checks if not c.passed]

    def test_an_id_already_in_the_graph_is_refused(self, context):
        checks, _ = check(Candidate("Malachite"), proposed(), context, FakeWeb())
        assert "id_is_new" in [c.name for c in checks if not c.passed]


class TestCurating:
    """Whole runs over the repository's queue, with nothing accepted: nothing reaches git."""

    def test_an_unsure_proposer_ends_the_item_with_no_review(self, repo_root, built_dir, fake_claude, tmp_path):
        fake_claude.script(proposer=[answer(UNSURE)])
        report = run(repo_root, built_dir, fake_claude, audit_dir=tmp_path / "audit", items=1)
        assert [(r.item.name, r.outcome, r.reason) for r in report.results] == [("Galena", "unsure", "No source says.")]
        assert fake_claude.calls("reviewer") == []

    def test_a_failed_check_goes_back_to_the_proposer_with_the_reasons(self, repo_root, built_dir, fake_claude, tmp_path):
        # given: a class no row has shown how to mine yet, then "unsure"
        fake_claude.script(proposer=[answer(GOOD | {"class": "tin-ore"}), answer(UNSURE | {"unsure_why": "Gave up."})])
        report = run(repo_root, built_dir, fake_claude, audit_dir=tmp_path / "audit", items=1)
        second = fake_claude.calls("proposer")[1]["prompt"]
        assert "Your last proposal for this mineral was sent back" in second and "class_is_known" in second
        assert report.results[0].outcome == "unsure"

    def test_the_reviewer_sees_the_downloaded_page_but_not_what_the_proposer_was_offered(self, repo_root, built_dir,
                                                                                        fake_claude, tmp_path):
        fake_claude.script(proposer=[answer(GOOD)], reviewer=[{"output": {"verdict": "reject", "objections": [
            {"about": "class", "objection": "Galena is a lead ore."}], "summary": "Wrong class."}}])
        report = run(repo_root, built_dir, fake_claude, audit_dir=tmp_path / "audit", items=1)
        proposer, review = fake_claude.calls("proposer")[0]["prompt"], fake_claude.calls("reviewer")[0]["prompt"]
        assert "[1] From: Ada Example (2021). Lead ores at an example site. Example Journal. (OpenAlex" in proposer
        assert "Notes on ores. " + GALENA_SENTENCE in review and "[1] From:" not in review
        assert (report.results[0].outcome, report.results[0].attempts) == ("rejected", 1)
        assert "Galena is a lead ore." in report.results[0].reason

    def test_revisions_are_bounded(self, repo_root, built_dir, fake_claude, tmp_path):
        revise = {"output": {"verdict": "revise", "objections": [{"about": "supports", "objection": "Too broad."}],
                             "summary": "Narrow it."}}
        fake_claude.script(proposer=[answer(GOOD), answer(GOOD)], reviewer=[revise, revise])
        report = run(repo_root, built_dir, fake_claude, audit_dir=tmp_path / "audit", items=1)
        assert (report.results[0].outcome, report.results[0].attempts) == ("sent_back", 2)
        assert "supports: Too broad." in fake_claude.calls("proposer")[1]["prompt"]

    def test_an_agent_failure_costs_one_item_not_the_run(self, repo_root, built_dir, fake_claude, tmp_path):
        fake_claude.script(proposer=[{"error": "max_turns"}, answer(UNSURE)])
        report = run(repo_root, built_dir, fake_claude, audit_dir=tmp_path / "audit", items=2)
        assert [r.outcome for r in report.results] == ["failed", "unsure"]

    def test_a_failed_calls_use_of_the_plan_counts_toward_stopping(self, repo_root, built_dir, fake_claude, tmp_path):
        # given: the first item's proposer runs out of turns, having used the plan up to 85%
        fake_claude.script(proposer=[{"error": "max_turns", "five_hour": 0.85}])
        report = run(repo_root, built_dir, fake_claude, audit_dir=tmp_path / "audit", items=3, stop_at_five_hour=0.8)
        # then: the run stops before the next item, and the call's usage is in the audit log
        assert [r.outcome for r in report.results] == ["failed"] and "85%" in report.stopped_because
        assert report.summary["usage"]["calls"] == 1
        assert audit_rows(tmp_path / "audit", "select json_extract_string(limits, '$.five_hour'), error is not null "
                                              "from calls") == [("0.85", True)]

    def test_reaching_the_plans_limit_stops_the_run_and_leaves_the_rest(self, repo_root, built_dir, fake_claude, tmp_path):
        fake_claude.script(proposer=[answer(UNSURE), {"limit": True}])
        report = run(repo_root, built_dir, fake_claude, audit_dir=tmp_path / "audit", items=5)
        assert [r.item.name for r in report.results] == ["Galena"]
        assert "usage limit was reached" in report.stopped_because
        assert len(fake_claude.calls()) == 2

    def test_a_run_stops_before_the_next_item_once_usage_passes_its_threshold(self, repo_root, built_dir, fake_claude,
                                                                              tmp_path):
        fake_claude.script(proposer=[answer(UNSURE, five_hour=0.85)])
        report = run(repo_root, built_dir, fake_claude, audit_dir=tmp_path / "audit", items=5, stop_at_five_hour=0.8)
        assert len(report.results) == 1 and "five-hour usage reached 85%" in report.stopped_because

    def test_every_call_check_and_outcome_is_in_the_audit_log(self, repo_root, built_dir, fake_claude, tmp_path):
        fake_claude.script(proposer=[answer(GOOD | {"class": "tin-ore"}), answer(UNSURE)])
        report = run(repo_root, built_dir, fake_claude, audit_dir=tmp_path / "audit", items=1)
        audit = tmp_path / "audit"
        calls = audit_rows(audit, "select role, attempt, json_extract_string(settings, '$.model'), "
                                  "json_extract_string(settings, '$.effort'), json_extract_string(settings, '$.model_id') "
                                  "from calls order by attempt")
        assert calls == [("proposer", 1, "sonnet", "medium", "claude-opus-5-5"),
                         ("proposer", 2, "sonnet", "medium", "claude-opus-5-5")]
        checks = audit_rows(audit, "select name, passed, detail from checks order by recorded_at")
        assert checks[:2] == [("wikidata_item_found", True, "Q99999910 (galena). The search found: Q99999910 'galena' "
                                                            "(lead sulfide mineral; instance of Q12089225 'mineral species'; "
                                                            "subclass of nothing): taken"),
                              ("passages_found", True, "1 passages from 1 sources (1 read) (OpenAlex)")]
        assert ("class_is_known", False) in [(name, passed) for name, passed, _ in checks]
        assert audit_rows(audit, "select item, outcome from outcomes") == [("Galena", "unsure")]
        assert audit_rows(audit, "select run_id, mode, json_extract_string(login, '$.plan') from run_starts") == [
            (report.run_id, "propose", "pro")]
        assert audit_rows(audit, "select count(*) from run_ends") == [(1,)]
        summary = json.loads((audit / "runs" / f"{report.run_id}.json").read_text())
        assert summary["usage"]["calls"] == 2
        # Code made the searches: two OpenAlex searches for the one item, and every page read once
        assert summary["sources"]["openalex_searches"] == 2 and summary["sources"]["pages_downloaded"] >= 1
        assert summary["model_ids"] == {"proposer": "claude-opus-5-5"} and summary["failed_because"] is None

    def test_a_run_that_breaks_still_records_its_end_and_its_summary(self, repo_root, built_dir, fake_claude, tmp_path):
        class Broken(FakeWeb):
            def page(self, url):
                raise RuntimeError("a bug in reading pages")

        fake_claude.script(proposer=[answer(GOOD)])
        with pytest.raises(RuntimeError):
            run(repo_root, built_dir, fake_claude, web=Broken(), audit_dir=tmp_path / "audit", items=1)
        ends = audit_rows(tmp_path / "audit", "select run_id, stopped_because from run_ends")
        assert len(ends) == 1 and ends[0][1] == "RuntimeError: a bug in reading pages"
        summary = json.loads((tmp_path / "audit" / "runs" / f"{ends[0][0]}.json").read_text())
        assert summary["failed_because"] == "RuntimeError: a bug in reading pages" and summary["usage"]["calls"] == 0

    @pytest.mark.parametrize("changes", [
        pytest.param({"stop_at_five_hour": 80}, id="a five-hour threshold given as a percentage"),
        pytest.param({"stop_at_seven_day": 0}, id="a weekly threshold of nothing"),
        pytest.param({"items": 0}, id="no items"),
        pytest.param({"proposer_effort": "hard"}, id="an effort Claude Code doesn't have"),
    ])
    def test_settings_that_would_never_stop_or_never_start_are_refused(self, fake_claude, changes):
        with pytest.raises(ValueError):
            settings(fake_claude, **changes)


class TestFindingSources:
    """Code finds the item and the passages; a model only chooses among them."""

    def test_the_item_is_the_mineral_species_called_exactly_its_name(self):
        town = WikidataItem("Q99999920", "Galena", "town in Kansas", instance_of=("Q3957",))
        web = FakeWeb(items={town.id: town})
        assert Library(web, []).item_for("Galena").item.id == GALENA_ITEM.id
        # with no mineral of that name, there's no item, and each hit is recorded with why it wasn't taken
        lookup = Library(FakeWeb(items={GALENA_ITEM.id: None, town.id: town}), []).item_for("Galena")
        assert lookup.item is None and lookup.seen == (
            "Q99999920 'Galena' (town in Kansas; instance of Q3957; subclass of nothing): neither a mineral species nor "
            "a subclass of a class of minerals",)

    def test_a_kind_of_mineral_filed_as_a_subclass_of_a_class_of_minerals_is_a_mineral(self):
        # Wikidata files limonite and native gold under a class of minerals, not as instances of mineral species
        oxides = WikidataItem("Q99999930", "oxide class of minerals", None, instance_of=("Q1",))
        brown = WikidataItem("Q99999931", "brownite", "hydrated iron oxide mineral", instance_of=("Q2",),
                             subclass_of=(oxides.id,))
        assert Library(FakeWeb(items={oxides.id: oxides, brown.id: brown}), []).item_for("Brownite").item.id == brown.id

    def test_a_lookup_reads_only_the_classes_its_decision_needs(self):
        # given: what a search for "Gold" returns: an album called Gold, and the element, a subclass of noble metals
        album = WikidataItem("Q99999950", "Gold", "studio album", instance_of=("Q99999951",))
        element = WikidataItem("Q99999952", "gold", "chemical element", instance_of=("Q11344",), subclass_of=("Q99999953",))
        web = FakeWeb(items={album.id: album, element.id: element})
        lookup = Library(web, []).item_for("Gold")
        # then: the element's parent was read, to see whether it is a class of minerals, and nothing else was
        assert lookup.item is None
        assert set(web.items_asked) == {album.id, element.id, "Q99999953"}
        assert "Q99999952 'gold' (chemical element; instance of Q11344 'chemical element'; subclass of Q99999953): " \
               "neither a mineral species nor a subclass of a class of minerals" in lookup.seen

    def test_a_native_metal_is_found_as_native_when_its_name_finds_only_the_element(self):
        element = WikidataItem("Q99999940", "silver", "chemical element", instance_of=("Q11344",))
        native = WikidataItem("Q99999941", "native silver", "mineral")
        lookup = Library(FakeWeb(items={element.id: element, native.id: native}), []).item_for("Silver")
        assert lookup.item.id == native.id and any(s.startswith("Q99999940 'silver'") for s in lookup.seen)

    def test_a_mineral_already_in_the_graph_is_left_to_a_person(self, repo_root, built_dir, fake_claude, tmp_path):
        # given: Limonite's item is a curated thing's (wikidata_things.csv), as the real one is
        limonite = WikidataItem("Q193565", "limonite", "hydrated iron oxide mineral")
        fake_claude.script()
        report = run(repo_root, built_dir, fake_claude, web=FakeWeb(items={limonite.id: limonite}),
                     audit_dir=tmp_path / "audit", items=1, names=("Limonite",))
        assert report.results[0].outcome == "skipped" and "a curated thing's item" in report.results[0].reason
        assert fake_claude.calls() == []

    def test_a_mineral_already_decided_is_skipped_as_decided(self, repo_root, built_dir, fake_claude, tmp_path):
        # given: azurite's real item, which the crosswalk already has a row for
        azurite = WikidataItem("Q108212", "azurite", "copper carbonate mineral")
        fake_claude.script()
        report = run(repo_root, built_dir, fake_claude, web=FakeWeb(items={azurite.id: azurite}),
                     audit_dir=tmp_path / "audit", items=1, names=("Azurite",))
        assert report.results[0].reason == "Q108212 (azurite) is already decided: ore_minerals.csv has a row for it"

    def test_an_evaluation_says_which_named_minerals_it_has_no_answer_for(self, repo_root, built_dir, fake_claude,
                                                                          tmp_path):
        fake_claude.script()
        report = run(repo_root, built_dir, fake_claude, audit_dir=tmp_path / "audit", items=5, evaluate=True,
                     find_only=True, names=("Pyrite", "Pyrrite"))
        assert [r.item.name for r in report.results] == ["Pyrite"]
        assert report.summary["not_evaluated"] == ["Pyrrite"]

    def test_named_minerals_run_in_the_order_named_whether_or_not_the_queue_lists_them(self, repo_root, built_dir,
                                                                                    fake_claude, tmp_path):
        fake_claude.script()
        report = run(repo_root, built_dir, fake_claude, audit_dir=tmp_path / "audit", items=5, find_only=True,
                     names=("Sphalerite", "Unobtanium", "Galena"))
        assert [(r.item.name, r.outcome) for r in report.results] == [
            ("Sphalerite", "found"), ("Unobtanium", "skipped"), ("Galena", "found")]
        assert report.results[1].item.detail == "Named for this run; the curation queue doesn't list it."

    def test_passages_name_the_mineral_and_speak_of_ore_with_the_sentences_around_them(self):
        text = ("Galena is grey. It was mined near the river. Galena was roasted in heaps be-\nfore it was smelted for "
                "silver and lead. The slag was dumped nearby.")
        web = FakeWeb(pages={GALENA_URL: Page(GALENA_URL, "200", text, None, "pdf")})
        found = galena_passages(Library(web, []))
        [passage] = found.passages  # "Galena is grey." names it but says nothing of ore
        assert passage.sentence == "Galena was roasted in heaps before it was smelted for silver and lead."
        assert (passage.before, passage.after) == ("It was mined near the river.", "The slag was dumped nearby.")
        # and the sentence, mended where the PDF broke a word, is still found on the page word for word
        assert locate(passage.sentence, text) is not None

    def test_on_a_tie_the_repositorys_own_source_comes_first_and_each_page_is_read_once(self):
        known = Source("Known, K. (2000). A page we cite.", "https://example.org/known", "cited in the repository")
        page = Page(known.url, "200", GALENA_SENTENCE, None, "text")  # as good a sentence as the OpenAlex work's
        web = FakeWeb(pages={known.url: page})
        library = Library(web, [known])
        found = galena_passages(library)
        library.page(GALENA_URL)  # as the checks read it again
        assert [(p.number, p.source.origin) for p in found.passages] == [(1, "cited in the repository"), (2, "OpenAlex")]
        assert web.asked.count(GALENA_URL) == 1 and web.searched == ["Galena archaeometallurgy", "Galena ancient smelting"]

    def test_passages_are_ranked_across_sources_so_a_better_one_read_later_isnt_crowded_out(self):
        # given: twelve pages the repository cites, each with weak sentences (galena in a slag), read before the
        # OpenAlex work that says it was roasted and smelted
        weak = " ".join(f"Galena grains number {n} were seen in the copper slag." for n in "ABC")
        known = [Source(f"Page {n}.", f"https://example.org/known-{n}", "cited in the repository") for n in range(12)]
        web = FakeWeb(pages={s.url: Page(s.url, "200", weak, None, "text") for s in known})
        found = galena_passages(Library(web, known))
        assert len(found.passages) == 12 and found.passages[0].sentence == GALENA_SENTENCE

    @pytest.mark.parametrize("line", [
        pytest.param("Journal of Ores 12:1114–1127 https://doi.org/10.1/x Galena smelting at the example site.", id="a header"),
        pytest.param("Keywords: galena, smelting, lead, slag, furnace, roasting, silver, cupellation.", id="keywords"),
        pytest.param("Smith J, Jones K (2001) Galena ores and their smelting in the example valley.", id="a reference"),
        pytest.param("Figure 9: Galena ore from the example mine, before and after roasting for smelting.", id="a caption"),
        pytest.param("Table IV. Galena, chalcopyrite and the other sulphide ores smelted at each of the sites.",
                     id="a table's title"),
    ])
    def test_a_line_that_isnt_prose_isnt_offered(self, line):
        text = line + "\n" + "In antiquity galena was roasted and then smelted in small furnaces for its lead."
        web = FakeWeb(pages={GALENA_URL: Page(GALENA_URL, "200", text, None, "html")})
        found = galena_passages(Library(web, []))
        assert [p.sentence for p in found.passages] == [
            "In antiquity galena was roasted and then smelted in small furnaces for its lead."]

    @pytest.mark.parametrize("sentence", [
        pytest.param("For copper smelting the main ores were sulphides like galena PbS (Fig. 2) and others.",
                     id="a figure reference"),
        pytest.param("Galena ores were smelted by other experimentalists (Crew 1991; Tylecote et al. 1971) in shafts.",
                     id="et al."),
        pytest.param("As J. R. Smith showed, galena was roasted before it was smelted for its lead.", id="initials"),
    ])
    def test_a_sentence_isnt_cut_off_at_an_abbreviation(self, sentence):
        # Two accepted quotes ended mid-sentence at "(Fig." and "et al." (Chalcopyrite and Siderite, 2026-11-25)
        text = "The site lies in the hills. " + sentence + " The slag was dumped nearby."
        web = FakeWeb(pages={GALENA_URL: Page(GALENA_URL, "200", text, None, "html")})
        assert [p.sentence for p in galena_passages(Library(web, [])).passages] == [sentence]

    @pytest.mark.parametrize("authors, citation", [
        pytest.param(["Ada Example"], "Ada Example (2021). Lead ores. Example Journal.", id="one author"),
        pytest.param(["Ada Example", "Bo Sample"], "Ada Example & Bo Sample (2021). Lead ores. Example Journal.",
                     id="two"),
        pytest.param(["Ada Example", "Bo Sample", "Cy Test"], "Ada Example, Bo Sample & Cy Test (2021). Lead ores. "
                     "Example Journal.", id="three"),
        pytest.param(["Ada Example", "Bo Sample", "Cy Test", "Di Trial"], "Ada Example et al. (2021). Lead ores. "
                     "Example Journal.", id="more than three"),
        # names as OpenAlex gives them: no guess at which part is the surname
        pytest.param(["Seyed Mohammadamin Emami"], "Seyed Mohammadamin Emami (2021). Lead ores. Example Journal.",
                     id="a name of three parts"),
    ])
    def test_a_citation_is_made_from_openalexs_record_not_written_by_a_model(self, authors, citation):
        work = {"display_name": "Lead ores", "publication_year": 2021, "primary_location": {
            "source": {"display_name": "Example Journal"}}, "authorships": [{"author": {"display_name": a}} for a in authors]}
        assert openalex_citation(work) == citation

    def test_the_proposal_takes_its_quote_citation_and_url_from_the_chosen_passage(self):
        found = galena_passages(Library(FakeWeb(), []))
        proposal = Proposal.from_choice(GOOD, GALENA_ITEM, found.passages)
        assert (proposal.wikidata, proposal.quote, proposal.url) == (GALENA_ITEM.id, GALENA_SENTENCE, GALENA_URL)
        assert proposal.citation == "Ada Example (2021). Lead ores at an example site. Example Journal."

    @pytest.mark.parametrize("web, reason", [
        pytest.param(FakeWeb(items={GALENA_ITEM.id: None}), "no Wikidata item is called 'Galena'", id="no item"),
        pytest.param(FakeWeb(works={"galena": []}), "no source found speaks of it as an ore", id="no passages"),
    ])
    def test_a_mineral_with_nothing_to_judge_is_skipped_without_asking_a_model(self, repo_root, built_dir, fake_claude,
                                                                             tmp_path, web, reason):
        fake_claude.script()
        report = run(repo_root, built_dir, fake_claude, web=web, audit_dir=tmp_path / "audit", items=1)
        assert report.results[0].outcome == "skipped" and report.results[0].reason.startswith(reason)
        assert fake_claude.calls() == []

    def test_a_find_only_run_records_what_it_would_offer_and_asks_no_model(self, repo_root, built_dir, fake_claude,
                                                                           tmp_path):
        fake_claude.script()
        report = run(repo_root, built_dir, fake_claude, audit_dir=tmp_path / "audit", items=2, find_only=True)
        assert [r.outcome for r in report.results] == ["found", "found"] and fake_claude.calls() == []
        assert GALENA_SENTENCE in report.results[0].reason

    def test_openalex_refusing_searches_stops_the_run_rather_than_skipping_items(self, repo_root, built_dir, fake_claude,
                                                                                tmp_path):
        import urllib.error

        class Spent(FakeWeb):
            def openalex_works(self, search, count):
                raise urllib.error.HTTPError("https://api.openalex.org/works", 429, "Too Many Requests", {}, None)

        fake_claude.script()
        report = run(repo_root, built_dir, fake_claude, web=Spent(), audit_dir=tmp_path / "audit", items=3)
        assert report.results == [] and "OpenAlex refused a search" in report.stopped_because

    def test_an_evaluation_doesnt_offer_a_source_only_the_persons_rows_cite(self, repo_root):
        penn = "https://www.penn.museum/sites/expedition/adventures-in-experimental-smelting/"
        assert penn in {s.url for s in known_sources(repo_root)}
        assert penn not in {s.url for s in known_sources(repo_root, frozenset({"Magnetite", "Goethite"}))}


class TestEvaluating:
    def test_the_evaluation_set_is_what_a_person_decided_in_the_crosswalk(self, repo_root):
        with (repo_root / "data" / "crosswalks" / "ore_minerals.csv").open(newline="", encoding="utf-8") as file:
            decided = {row["mrds_ore"]: row for row in csv.DictReader(file) if not row["proposed_by"]}
        for candidate, expected in evaluation_set():
            assert (expected["wikidata"], expected["class"]) == (decided[candidate.name]["wikidata"],
                                                                 decided[candidate.name]["class"])

    def test_an_evaluation_treats_the_persons_rows_as_undecided(self, repo_root):
        context = Context.of(repo_root, leaving_out=frozenset({"Azurite"}))
        assert "Q108212" not in context.taken_items and "azurite" not in context.taken_ids

    def test_the_score_counts_wrong_answers_that_got_through(self):
        from capabilities_pipeline.agents.curate import ItemResult

        answers = {"Pyrite": {"class": "none", "wikidata": "Q50769"}, "Bornite": {"class": "copper-sulphide-ore",
                                                                                 "wikidata": "Q108694"}}
        results = [
            ItemResult(Candidate("Pyrite"), "accepted", "", 1, Proposal("propose", "Q50769", "iron-ore")),
            ItemResult(Candidate("Bornite"), "accepted", "", 1, Proposal("propose", "Q108694", "copper-sulphide-ore")),
        ]
        assert score(results, answers) == {"items": 2, "proposed": 2, "right": 1, "accepted": 2, "accepted_right": 1,
                                           "accepted_wrong": 1}


class TestThePullRequestText:
    def test_text_from_a_page_or_an_agent_notifies_nobody(self):
        row = {"class": "copper-ore", "wikidata": "Q1", "citation": "Blog of @someone", "url": PAGE_URL,
               "quote": "As @someone showed, covellite was smelted."}
        summary = {
            "run": "ore-1", "models": {"proposer": "opus", "reviewer": "opus"}, "model_ids": {"proposer": "claude-opus-5-5"},
            "prompts": {"proposer": "a", "reviewer": "b"},
            "usage": {"calls": 2, "web_searches": 0, "web_fetches": 0, "first_limits": {}, "limits": {}},
            "sources": {"openalex_searches": 4, "pages_downloaded": 3},
            "items": [{"item": "Covellite", "outcome": "accepted", "reason": "", "change": row},
                      {"item": "Galena", "outcome": "rejected", "reason": "@reviewer said no", "change": None}],
        }
        body = pull_request_body(summary, OreCandidates(None, None))
        # then: no @ is followed by a name, so GitHub mentions nobody; a reader still sees "@someone"
        assert re.search(r"@\w", body) is None
        assert body.count("@\u2060someone") == 2 and "@\u2060reviewer" in body
        assert "proposer `opus` (`claude-opus-5-5`)" in body


class TestPrompts:
    def test_a_prompt_without_its_task_is_refused(self, tmp_path, monkeypatch):
        (tmp_path / "broken.md").write_text("You review minerals.\n\nThe mineral: $name.\n")
        monkeypatch.setattr(task_module, "PROMPTS", tmp_path)
        with pytest.raises(ValueError, match="---task---"):
            Prompt.load("broken")

    def test_the_prompts_in_the_repository_have_their_tasks(self):
        assert Prompt.load("ore_proposer").task.template and Prompt.load("ore_reviewer").task.template


class TestTheRepository:
    def test_the_agents_classes_are_the_crosswalks(self, repo_root):
        sources = yaml.safe_load((repo_root / "pipeline" / "dbt" / "models" / "staging" / "_sources.yml").read_text())
        table = next(t for s in sources["sources"] for t in s["tables"] if t["name"] == "ore_minerals")
        column = next(c for c in table["columns"] if c["name"] == "class")
        accepted = next(t["accepted_values"] for t in column["data_tests"] if isinstance(t, dict))
        assert tuple(accepted["arguments"]["values"]) == ORE_CLASSES

    def test_every_row_an_agent_proposed_has_its_runs_summary(self, repo_root):
        with (repo_root / "data" / "crosswalks" / "ore_minerals.csv").open(newline="", encoding="utf-8") as file:
            runs = {row["proposed_by"] for row in csv.DictReader(file) if row["proposed_by"]}
        assert [run for run in runs if not (repo_root / "data" / "agent_runs" / f"{run}.json").is_file()] == []

    def test_rewriting_the_crosswalk_changes_nothing_but_what_it_was_given(self, repo_root, tmp_path):
        crosswalk = tmp_path / "data" / "crosswalks" / "ore_minerals.csv"
        crosswalk.parent.mkdir(parents=True)
        shutil.copy(repo_root / "data" / "crosswalks" / "ore_minerals.csv", crosswalk)
        write_crosswalk(tmp_path, [])
        assert crosswalk.read_bytes() == (repo_root / "data" / "crosswalks" / "ore_minerals.csv").read_bytes()


# --- A whole run that opens a pull request: a throwaway repository, its "origin", and gh, all local -------------------

# Wikidata's labels for the made-up items, as the stand-in answers them.
NEW_ITEMS = [("Q99999911", "sphalerite", "zinc sulfide mineral", "ZnS"), ("Q99999912", "gold", "native gold", None)]
# OpenAlex's made-up records for the made-up sources, and the citations code makes of them.
WEB_PAGE_WORK = {"id": "W2", "display_name": "Ores of the example valley (web page)", "authorships": [],
                 "primary_location": {"source": {"display_name": "Example Museum"}}}
BOOK_WORK = {"id": "W3", "display_name": "A book no index lists", "publication_year": 1999,
             "authorships": [{"author": {"display_name": "A Nobody"}}],
             "primary_location": {"source": {"display_name": "Nowhere Press"}}}
WEB_PAGE_CITATION = "Ores of the example valley (web page). Example Museum."
UNLISTED_BOOK = "A Nobody (1999). A book no index lists. Nowhere Press."


def _git(directory: Path, *arguments: str) -> str:
    return subprocess.run(["git", "-C", str(directory), *arguments], capture_output=True, text=True,
                          check=True).stdout.strip()


def _repository(repo_root: Path, directory: Path) -> Path:
    """A copy of the repository's data in git, pushed to a local bare "origin". The backups a run refreshes are copied;
    the rest are linked, read-only."""
    repo = directory / "repo"
    for name in ("schema", "data", "examples"):
        shutil.copytree(repo_root / name, repo / name)
    shutil.copy(repo_root / "CREDITS.md", repo / "CREDITS.md")
    (repo / "snapshots").mkdir()
    for dataset in (repo_root / "snapshots").iterdir():
        if dataset.name in ("wikidata_quantities", "wikidata_items", "reference_candidates"):
            shutil.copytree(dataset, repo / "snapshots" / dataset.name)
        elif dataset.is_dir():
            (repo / "snapshots" / dataset.name).symlink_to(dataset, target_is_directory=True)
    _git(directory, "init", "-q", "-b", "main", str(repo))
    _git(repo, "config", "user.email", "tests@example.org")
    _git(repo, "config", "user.name", "Tests")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "The data")
    _git(directory, "init", "-q", "--bare", str(directory / "origin.git"))
    _git(repo, "remote", "add", "origin", str(directory / "origin.git"))
    _git(repo, "push", "-q", "origin", "main")
    return repo


def _fake_gh(directory: Path) -> Path:
    gh = directory / "gh"
    gh.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" >> "{directory / "gh-calls.txt"}"\n'
                  'if [ "$1" = "pr" ]; then echo "https://github.com/example/capabilities/pull/99"; fi\n')
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    return gh


@pytest.fixture(scope="module")
def published(repo_root, tmp_path_factory, wikidata_endpoint, scholarly_endpoint, lookups_offline):
    """One run over the top three ore candidates of a throwaway repository: Galena rejected as an ore (citing a web
    page), Sphalerite proposed as a copper sulphide citing a web page, and Gold as an iron ore citing a book no index
    lists (both made up, for the test). The agents accept all three, and all three pass the gate: Gold's book isn't
    found, which is noted, not held against it."""
    directory = tmp_path_factory.mktemp("published")
    repo = _repository(repo_root, directory)
    fake = FakeClaude(directory / "fake-claude")
    pages = {
        "https://example.org/galena": Page("https://example.org/galena", "200",
                                           "Galena is the chief ore of lead, not of copper.", None, "text"),
        "https://example.org/sphalerite": Page("https://example.org/sphalerite", "200",
                                               "Sphalerite was roasted with the copper sulphides at the example mine.",
                                               None, "text"),
        "https://example.org/gold": Page("https://example.org/gold", "200",
                                         "Gold was smelted with the iron ores of the example valley.", None, "text"),
    }
    items = {"Q99999910": WikidataItem("Q99999910", "galena", "lead sulfide mineral"),
             "Q99999911": WikidataItem("Q99999911", "sphalerite", "zinc sulfide mineral"),
             "Q99999912": WikidataItem("Q99999912", "gold", "native gold")}
    works = {"galena": [WEB_PAGE_WORK | {"best_oa_location": {"landing_page_url": "https://example.org/galena"}}],
             "sphalerite": [WEB_PAGE_WORK | {"best_oa_location": {"landing_page_url": "https://example.org/sphalerite"}}],
             "gold": [BOOK_WORK | {"best_oa_location": {"landing_page_url": "https://example.org/gold"}}]}
    choice = lambda ore_class, slug: answer(GOOD | {"class": ore_class, "supports": f"What the {slug} page says."})  # noqa: E731
    fake.script(
        proposer=[choice("none", "galena"), choice("copper-sulphide-ore", "sphalerite"), choice("iron-ore", "gold")],
        reviewer=[answer(ACCEPT)] * 3,
    )
    gh = _fake_gh(directory)
    with pytest.MonkeyPatch.context() as patch, lookups_offline():
        for name, value in fake.environment().items():
            patch.setenv(name, value)
        for name in claude_module.API_CREDENTIALS:
            patch.delenv(name, raising=False)
        wikidata_endpoint.extra_items.extend(NEW_ITEMS)
        try:
            report = run_agents(
                repo, directory / "build",
                replace(settings(fake, items=3, names=("Galena", "Sphalerite", "Gold")), pull_request=True,
                        gh_command=str(gh)),
                Downloads(wikidata_endpoint.url, scholarly_endpoint.openalex_url, scholarly_endpoint.crossref_url),
                web=FakeWeb(pages=pages, items=items, works=works), on_progress=lambda message: None, audit_dir=directory / "audit",
            )
            build_dir_setting = os.environ.get("CAPABILITIES_BUILD_DIR")
        finally:
            for item in NEW_ITEMS:
                wikidata_endpoint.extra_items.remove(item)
    branch = f"agents/{report.run_id}"
    show = lambda path: _git(directory / "origin.git", "show", f"{branch}:{path}")  # noqa: E731
    subject = _git(directory / "origin.git", "log", "-1", "--format=%s", branch)
    return {"report": report, "repo": repo, "show": show, "subject": subject, "gh": (directory / "gh-calls.txt").read_text().splitlines(),
            "audit": directory / "audit", "branch": branch, "build_dir_setting": build_dir_setting,
            "build_dir": directory / "build"}


class TestThePullRequest:
    def test_the_rows_that_pass_are_pushed_on_their_own_branch_and_opened_as_a_draft(self, published):
        assert published["report"].pull_request == "https://github.com/example/capabilities/pull/99"
        gh = published["gh"]
        assert gh[:2] == ["auth", "status"]
        assert ["pr", "create", "--draft", "--base", "main", "--head", published["branch"]] == gh[2:9]

    def test_the_commit_is_a_conventional_one_and_the_title_reads_plainly(self, published):
        run_id = published["report"].run_id
        assert published["subject"] == f"feat(data): agent proposals for 3 ore minerals (run {run_id})"
        gh = published["gh"]
        assert gh[gh.index("--title") + 1] == f"Agent proposals: 3 ore minerals (run {run_id})"

    def test_each_row_is_unverified_and_names_its_run_and_quote(self, published):
        rows = {row["mrds_ore"]: row for row in csv.DictReader(
            published["show"]("data/crosswalks/ore_minerals.csv").splitlines())}
        sphalerite = rows["Sphalerite"]
        assert (sphalerite["id"], sphalerite["class"], sphalerite["mined_like"]) == (
            "sphalerite", "copper-sulphide-ore", "mine-malachite")
        assert sphalerite["status"] == "" and sphalerite["proposed_by"] == published["report"].run_id
        assert sphalerite["quote"] == "Sphalerite was roasted with the copper sulphides at the example mine."
        assert (rows["Galena"]["id"], rows["Galena"]["class"]) == ("", "none")

    def test_a_work_no_index_lists_isnt_held_against_its_row(self, published):
        # Many books, reports and web pages are in neither OpenAlex nor Crossref (ADR 0047); the row's page was read and
        # its quote found, so the row goes in, with what the check found noted.
        assert "Gold" in published["show"]("data/crosswalks/ore_minerals.csv")
        gold = next(r for r in published["report"].results if r.item.name == "Gold")
        assert gold.outcome == "accepted"
        assert gold.checks[-1].detail == "not_found; its page loaded and the quote is on it"

    @pytest.mark.parametrize("result, passes", [
        pytest.param("found", True, id="found"),
        pytest.param("possible", True, id="possibly found"),
        pytest.param("not_found", True, id="not found"),
        pytest.param("not_searched", True, id="a web page"),
        pytest.param("doi_disagrees", False, id="a DOI that leads to another work"),
    ])
    def test_only_a_wrong_doi_drops_a_row(self, result, passes):
        from capabilities_pipeline.agents.branch import work_check

        citation = "Example, A. (2020). Ores."
        checks = {citation: {"result": result, "note": "Why.", "match_service": None, "links": []}}
        assert work_check(citation, checks).passed is passes

    def test_a_rejected_minerals_reference_isnt_looked_up(self, published):
        galena = next(r for r in published["report"].results if r.item.name == "Galena")
        assert galena.checks[-1].detail == "not looked up: a rejected mineral's reference builds nothing"

    def test_the_commit_carries_the_runs_summary_the_refreshed_backups_and_the_works_cited(self, published):
        run_id = published["report"].run_id
        summary = json.loads(published["show"](f"data/agent_runs/{run_id}.json"))
        assert summary["run"] == run_id and summary["outcomes"] == {"accepted": 3}
        # The Wikidata download behind the backup asked for the new items, and not for the rejected mineral's.
        query = json.loads(published["show"]("snapshots/wikidata_items/snapshot.json"))["query"]
        assert "wd:Q99999911" in query and "wd:Q99999912" in query and "wd:Q99999910" not in query
        assert WEB_PAGE_CITATION in published["show"]("CREDITS.md") and UNLISTED_BOOK in published["show"]("CREDITS.md")

    def test_the_gates_build_leaves_dbt_pointed_at_the_repositorys_own_build(self, published):
        # The run builds the repository to read its queue, which points dbt there; the gate's build mustn't move it.
        assert Path(published["build_dir_setting"]).resolve() == published["build_dir"].resolve()

    def test_the_worktree_is_gone_and_the_users_checkout_untouched(self, published):
        repo = published["repo"]
        assert len(_git(repo, "worktree", "list").splitlines()) == 1
        assert _git(repo, "status", "--porcelain") == ""
        assert _git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "main"


class TestWhenTheWebFails:
    def test_wikidata_being_down_fails_a_check_not_the_run(self, context):
        class Down(FakeWeb):
            def wikidata_item(self, item):
                import urllib.error

                raise urllib.error.URLError("connection refused")

        checks, _ = check(COVELLITE, proposed(), context, Down())
        failed = {c.name: c.detail for c in checks if not c.passed}
        assert failed == {"wikidata_item_is_the_mineral": "Wikidata couldn't be reached: <urlopen error connection refused>"}

    @pytest.mark.parametrize("url", [
        pytest.param("http://127.0.0.1:8000/api/graph", id="this machine"),
        pytest.param("http://localhost:3070/", id="this machine by name"),
        pytest.param("http://192.168.1.1/", id="the local network"),
        pytest.param("http://169.254.169.254/latest/meta-data/", id="a cloud's metadata service"),
        pytest.param("http://[::1]/", id="this machine over IPv6"),
    ])
    def test_a_citation_never_leads_the_download_off_the_public_web(self, url):
        # Refused before connecting: nothing is listening at these in the tests, and nothing is asked of the network.
        page = Web().page(url)
        assert page.status.startswith("not a public web address") and not page.loaded

    def test_a_public_address_is_public(self):
        assert not_public("http://93.184.215.14/") is None

    def test_a_redirect_off_the_public_web_isnt_followed(self):
        import urllib.error
        import urllib.request

        from capabilities_pipeline.agents.web import _PublicRedirects

        request = urllib.request.Request("http://93.184.215.14/")
        with pytest.raises(urllib.error.URLError, match="not a public web address"):
            _PublicRedirects().redirect_request(request, None, 302, "Found", {}, "http://127.0.0.1:3070/")

    def test_a_page_in_a_charset_python_doesnt_know_is_read_as_utf8(self):
        page = read(PAGE_URL, "200", "Covellite – roasted.".encode(), "text/plain", "utf8mb4")
        assert page.text == "Covellite – roasted."


class TestCleaningUp:
    def test_a_cleanup_that_fails_neither_fails_the_run_nor_hides_its_error(self, tmp_path, caplog):
        repo = tmp_path / "repo"
        _git(tmp_path, "init", "-q", "-b", "main", str(repo))
        _git(repo, "-c", "user.email=t@example.org", "-c", "user.name=T", "commit", "-q", "--allow-empty", "-m", "first")
        # when: the run fails, after its branch was already deleted, so cleaning up can't delete it
        with pytest.raises(ValueError, match="the run's own error"):
            with Worktree(repo, "agents/test", "main", tmp_path / "worktree") as worktree:
                _git(worktree.root, "checkout", "-q", "--detach")
                _git(repo, "branch", "-D", "agents/test")
                raise ValueError("the run's own error")
        # then: the run's error is what is raised, the worktree is gone, and the leftover is only warned about
        assert not (tmp_path / "worktree").exists()
        assert "Couldn't delete the branch agents/test" in caplog.text


class TestTheDagsterJob:
    def test_a_run_is_a_job_launched_with_its_size_and_reports_what_happened(self, repo_root, built_dir, fake_claude,
                                                                              tmp_path, monkeypatch):
        from capabilities_pipeline.assets import definitions

        # given: the stand-in on the PATH as `claude`, and the audit log somewhere temporary
        monkeypatch.setenv("PATH", f"{fake_claude.command.parent}{os.pathsep}{os.environ['PATH']}")
        monkeypatch.setenv("CAPABILITIES_AUDIT_DIR", str(tmp_path / "audit"))
        for name in ("CAPABILITIES_BUILD_DIR", "DBT_LOG_PATH", "DBT_TARGET_PATH", "DO_NOT_TRACK"):
            monkeypatch.delenv(name, raising=False)
        fake_claude.script(proposer=[answer(UNSURE)])
        defs = definitions(repo_root, built_dir)
        # then: it is a job, not an asset, so materializing every asset never starts one
        assert "curate" not in {key.to_user_string() for key in defs.resolve_asset_graph().get_all_asset_keys()}
        # when: launched for one item, with no pull request
        # (Wikidata's site and OpenAlex pointed at a local port with nothing on it: the item can't be found, so the run
        # skips it without asking a model, and nothing reaches the network)
        result = defs.get_job_def("agent_curation").execute_in_process(run_config={
            "ops": {"curate": {"config": {"items": 1, "pull_request": False, "names": ["Galena"]}}},
            "resources": {"downloads": {"config": {"wikidata_site_url": "http://127.0.0.1:9",
                                                   "openalex_url": "http://127.0.0.1:9"}}}})
        # then: the run's outcome is in its output and in the audit log
        summary = result.output_for_node("curate")
        assert summary["outcomes"] == {"skipped": 1} and summary["items"][0]["item"] == "Galena"
        assert audit_rows(tmp_path / "audit", "select outcome from outcomes") == [("skipped",)]
        assert fake_claude.calls() == []
