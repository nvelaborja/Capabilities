import shutil

import pytest

from capabilities.cli import main
from capabilities.credits import END, START, cited_works, link_for, refreshed, works_cited_markdown


class TestCitedWorks:
    def test_a_work_cited_by_several_routes_is_listed_once_with_each_citer(self, graph):
        works = {work.citation: work for work in cited_works(graph)}
        clarke = next(work for citation, work in works.items() if citation.startswith("Clarke, S. & Engelbach"))
        assert {"quarry-granite", "collect-dolerite"} <= clarke.cited_by
        assert clarke.statuses == {"unverified"}

    def test_works_are_alphabetical_ignoring_case(self, graph):
        citations = [work.citation for work in cited_works(graph)]
        assert citations == sorted(citations, key=str.casefold)

    def test_a_doi_links_to_doi_org_before_any_url(self):
        assert link_for({"citation": "x", "doi": "10.1/abc", "url": "https://example.org"}) == "https://doi.org/10.1/abc"
        assert link_for({"citation": "x", "url": "https://example.org"}) == "https://example.org"
        assert link_for({"citation": "x"}) is None

    def test_the_section_counts_the_works_and_names_what_cites_them(self, graph):
        works = cited_works(graph)
        section = works_cited_markdown(works)
        assert section.startswith(f"{len(works)} works are cited")
        assert "*unverified*. Cited by `collect-dolerite`, `quarry-granite`, `shape-by-pounding`." in section


class TestRefreshed:
    def test_only_the_text_between_the_markers_changes(self):
        text = f"# Credits\n\nIntro.\n\n{START}\nold\n{END}\n\n## Software\n"
        assert refreshed(text, "new") == f"# Credits\n\nIntro.\n\n{START}\nnew\n{END}\n\n## Software\n"

    def test_missing_markers_are_an_error_not_a_silent_append(self):
        with pytest.raises(ValueError, match="markers"):
            refreshed("# Credits\n", "new")


class TestCreditsCommand:
    def test_the_repository_credits_are_up_to_date(self, repo_root, capsys):
        # A new or changed citation in the data must come with `uv run capabilities credits`.
        assert main(["--root", str(repo_root), "credits", "--check"]) == 0

    def test_check_fails_when_a_citation_is_missing_and_the_command_fixes_it(self, data_copy, repo_root, capsys):
        shutil.copy(repo_root / "CREDITS.md", data_copy / "CREDITS.md")
        stale = (data_copy / "CREDITS.md").read_text().replace("Ball, V. (1881)", "Someone else (1881)")
        (data_copy / "CREDITS.md").write_text(stale)

        assert main(["--root", str(data_copy), "credits", "--check"]) == 1
        assert main(["--root", str(data_copy), "credits"]) == 0
        assert main(["--root", str(data_copy), "credits", "--check"]) == 0
        assert "Ball, V. (1881)" in (data_copy / "CREDITS.md").read_text()
