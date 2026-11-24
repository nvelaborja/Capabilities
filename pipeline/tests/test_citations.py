"""Citation checks: every cited work looked up in OpenAlex and Crossref, and every cited link checked (ADR 0047).

Nothing here asks the real services: `scholarly_endpoint` (conftest) stands in for both, answering from the committed
backup, and links are answered from it too. `built_dir` and `graph` are built from the backups, so the checks below are
the real results of 2026-11-24.
"""

import duckdb
import pytest

from capabilities.built import load_queue, load_reference_checks
from capabilities.views import references
from capabilities_pipeline.build import build

TYLECOTE = "Tylecote, R. F. (1992). A History of Metallurgy, 2nd ed. Institute of Materials."
FALL = "Fall, A. et al. (2014). Sliding Friction on Wet and Dry Sand. Physical Review Letters 112, 175502."
NICHOLSON = "Nicholson, P. T. & Shaw, I. (eds.) (2000). Ancient Egyptian Materials and Technology. Cambridge University Press."
KLEMM = "Klemm, R. & Klemm, D. D. (2008). Stones and Quarries in Ancient Egypt. British Museum Press."
CRUCIBLE = "Crucible process. Encyclopaedia Britannica."
SARAYDAR_DOI = "10.2307/278680"


def rows(parquet) -> list[tuple]:
    return sorted(duckdb.sql("select * from read_parquet(?)", params=[str(parquet)]).fetchall(), key=str)


@pytest.fixture(scope="module")
def checks(built_dir) -> dict[str, dict]:
    return load_reference_checks(built_dir)


class TestLookingUp:
    def test_a_download_gives_back_what_the_services_answered_unchanged(self, tmp_path, repo_root, fetch_references):
        from capabilities_pipeline.upstream import REFERENCES, backup_directory

        # given: the stand-ins, answering what OpenAlex and Crossref answered on 2026-11-24
        snapshot = fetch_references(tmp_path)
        # then: the same rows as the backup made from the real download
        assert rows(REFERENCES.parquet(tmp_path)) == rows(backup_directory(REFERENCES, repo_root) / "reference_candidates.parquet")
        assert (snapshot["works"], snapshot["searched"]) == (43, 27)

    def test_each_work_is_looked_up_once_however_often_it_is_cited(self, repo_root):
        from capabilities_pipeline.citations import cited_works

        citations = [work.citation for work in cited_works(repo_root)]
        assert citations.count(TYLECOTE) == 1  # cited by eleven routes
        # The ore crosswalk's references count too.
        assert any(citation.startswith("Hamilton, E. G. (2007)") for citation in citations)

    def test_a_work_with_a_doi_is_looked_up_by_it_and_a_web_page_is_not_searched_for(self, tmp_path, fetch_references,
                                                                                    scholarly_endpoint):
        fetch_references(tmp_path)
        requests = scholarly_endpoint.requests
        assert "/openalex/works/doi:10.1103/PhysRevLett.112.175502" in {r.split("?")[0] for r in requests}
        assert "/crossref/works/10.1103/PhysRevLett.112.175502" in requests
        assert not any("Wikipedia" in request for request in requests)

    @pytest.mark.parametrize(("citation", "searched_for"), [
        (TYLECOTE, "A History of Metallurgy"),  # no edition
        ("Stocks, D. A. (1988). Industrial technology at Kahun and Gurob (MA thesis, University of Manchester), as "
         "summarized in 'Ancient Egyptian Copper Slabbing Saws', Hall of Ma'at.",
         "Industrial technology at Kahun and Gurob (MA thesis, University of Manchester)"),  # not the summary
        ("Experimental ironmaking papers, EXARC euroREA 6 (2009): 'A new look at experimental ironmaking'.",
         "A new look at experimental ironmaking"),
        ("Wealden Iron Research Group. Smelting experiments (2015).", "Wealden Iron Research Group. Smelting experiments"),
    ])
    def test_openalex_is_searched_for_the_title(self, citation, searched_for):
        from capabilities_pipeline.citations import search_text

        assert search_text(citation) == searched_for

    def test_no_abstract_is_kept(self):
        from capabilities_pipeline.citations import COLUMNS, _crossref_row

        # Crossref's abstracts can be copyrighted (ADR 0037).
        assert "abstract" not in COLUMNS
        assert "abstract" not in _crossref_row({"DOI": "10.1/x", "title": ["T"], "abstract": "<jats:p>…</jats:p>"})

    def test_offline_the_lookups_fall_back_to_the_cold_backup(self, tmp_path, repo_root, lookups_offline):
        from dataclasses import replace

        from capabilities_pipeline.upstream import REFERENCES, fetch_or_fall_back

        # given: port 9, which refuses connections, as a service that is down would
        dataset = replace(REFERENCES, crossref_url="http://127.0.0.1:9")
        with lookups_offline():
            snapshot, error = fetch_or_fall_back(dataset, repo_root, tmp_path, "http://127.0.0.1:9")
        assert (snapshot["copy"], snapshot["rows"]) == ("backup", 242)
        assert error


class TestChecks:
    def test_every_cited_work_has_a_check(self, checks, repo_root):
        from capabilities_pipeline.citations import cited_works

        assert set(checks) == {work.citation for work in cited_works(repo_root)}

    def test_a_work_found_with_its_title_first_author_and_year_links_its_record_and_a_free_copy(self, checks):
        fall = checks[FALL]
        assert (fall["result"], fall["match_service"], fall["match_year"]) == ("found", "openalex", 2014)
        assert fall["free_copy"] == "http://link.aps.org/pdf/10.1103/PhysRevLett.112.175502"

    def test_a_book_known_only_by_its_reviews_says_so(self, checks):
        assert checks[NICHOLSON]["result"] == "review_found"

    def test_another_edition_is_only_a_possible_match(self, checks):
        tylecote = checks[TYLECOTE]
        assert tylecote["result"] == "possible"
        assert tylecote["note"] == "the year differs (cited 1992, found 1978): perhaps another edition"

    def test_a_work_found_nowhere_isnt_called_doubtful(self, checks):
        wealden = checks["Wealden Iron Research Group. Smelting experiments (2015)."]
        assert wealden["result"] == "not_found"
        assert "doesn't make the work doubtful" in wealden["note"]

    def test_a_web_page_only_has_its_link_checked(self, checks):
        assert checks["Fire piston. Wikipedia."]["result"] == "not_searched"
        assert checks["Fire piston. Wikipedia."]["links"] == {"https://en.wikipedia.org/wiki/Fire_piston": "works"}
        # Britannica turns away anything that isn't a browser: the link isn't called broken.
        assert checks[CRUCIBLE]["links"] == {"https://www.britannica.com/technology/crucible-process": "refused"}


@pytest.fixture(scope="module")
def changed(tmp_path_factory, repo_root, fetch_references):
    """A copy of the data in which Fall's DOI is wrong (Saraydar's), Klemm is verified, and a citation is added after
    the works were looked up."""
    import shutil

    root = tmp_path_factory.mktemp("data")
    for directory in ("schema", "data", "examples"):
        shutil.copytree(repo_root / directory, root / directory)
    (root / "snapshots").symlink_to(repo_root / "snapshots", target_is_directory=True)
    sledge = root / "data" / "routes" / "move-on-sledge.yaml"
    sledge.write_text(sledge.read_text().replace("doi: 10.1103/PhysRevLett.112.175502", f"doi: {SARAYDAR_DOI}"))
    quarry = root / "data" / "routes" / "quarry-limestone.yaml"
    text = quarry.read_text()
    klemm = text.index(KLEMM)
    quarry.write_text(text[:klemm] + text[klemm:].replace("status: unverified", "status: verified", 1))
    build_dir = tmp_path_factory.mktemp("build")
    fetch_references(build_dir, root=root)
    # Cited after the lookup: no download since.
    quarry.write_text(quarry.read_text() + '  - citation: "Someone, A. (2026). A work cited today."\n'
                      "    supports: Nothing yet.\n    status: unverified\n")
    build(root, build_dir)
    return build_dir



class TestChangesSinceTheLookup:
    def test_a_doi_that_leads_to_a_different_work_is_flagged(self, changed):
        fall = load_reference_checks(changed)[FALL]
        assert fall["result"] == "doi_disagrees"
        assert fall["match_title"].startswith("A Quantitative Comparison of Efficiency")

    def test_a_work_cited_after_the_lookup_is_not_checked_yet_and_the_build_goes_on(self, changed):
        assert load_reference_checks(changed)["Someone, A. (2026). A work cited today."]["result"] == "not_checked_yet"

    def test_a_work_verified_everywhere_it_is_cited_leaves_the_reading_queue(self, changed):
        reading = {item["label"] for item in load_queue(changed) if item["kind"] == "unread_reference"}
        assert KLEMM not in reading
        assert TYLECOTE in reading


class TestReadingQueue:
    def test_works_not_yet_read_are_queued_the_most_depended_on_first(self, built_dir):
        reading = [item for item in load_queue(built_dir) if item["kind"] == "unread_reference"]
        assert len(reading) == 43  # nothing is verified yet
        assert reading[0]["priority"] == max(item["priority"] for item in reading)
        tylecote = next(item for item in reading if item["label"] == TYLECOTE)
        assert tylecote["detail"].startswith("Cited by 11 routes.")

    def test_reading_comes_after_the_ore_candidates_and_before_placing_materials(self, built_dir):
        kinds = list(dict.fromkeys(item["kind"] for item in load_queue(built_dir)))
        assert kinds.index("ore_candidate") < kinds.index("unread_reference") < kinds.index("unmatched_place")

    def test_a_free_copy_is_offered_in_the_queue(self, built_dir):
        fall = next(item for item in load_queue(built_dir) if item["label"] == FALL)
        assert "free copy: http://link.aps.org/pdf/10.1103/PhysRevLett.112.175502" in fall["detail"]


class TestInTheApp:
    def test_each_reference_carries_its_check_but_keeps_its_own_status(self, graph):
        (fall,) = [ref for ref in references(graph, graph.routes["move-on-sledge"]) if ref["citation"] == FALL]
        assert fall["status"] == "secondary"  # a check never changes it
        assert fall["check"]["result"] == "found"
        assert fall["check"]["match"]["service"] == "OpenAlex"
        assert fall["check"]["match"]["url"].startswith("https://openalex.org/W")

    def test_a_reference_says_how_its_own_link_answered(self, graph):
        (crucible,) = [ref for ref in references(graph, graph.routes["steel-by-crucible"]) if ref["citation"] == CRUCIBLE]
        assert crucible["check"] == {"result": "not_searched", "checked_at": "2026-11-24T21:45:44Z",
                                     "note": "A web page, or a work with no year: only its links are checked.",
                                     "link": "refused"}

    def test_the_curated_graph_has_no_checks(self, curated_graph):
        assert all("check" not in ref for ref in references(curated_graph, curated_graph.routes["move-on-sledge"]))
