import json

import pytest

from capabilities.cli import main


class TestCli:
    def test_validate_passes_on_repository_data(self, repo_root, built_dir, capsys):
        assert main(["--root", str(repo_root), "--build-dir", str(built_dir), "validate", "--quiet"]) == 0
        assert "0 errors" in capsys.readouterr().out

    def test_need_prints_tree_and_certain_needs(self, repo_root, built_dir, capsys):
        assert main(["--root", str(repo_root), "--build-dir", str(built_dir), "need", "steel"]) == 0
        out = capsys.readouterr().out
        assert "via steel-by-carburizing" in out
        assert "heat: duration_h >= 24, temperature_c >= 1100" in out

    def test_explore_json(self, repo_root, built_dir, capsys):
        assert main(["--root", str(repo_root), "--build-dir", str(built_dir), "explore", "--profile", "middle-kingdom-egypt", "--hypothetical", "hematite", "--json"]) == 0
        result = json.loads(capsys.readouterr().out)
        assert "steel" in result["reachable"]
        assert result["hypothetical"] == ["hematite"]

    def test_explore_says_where_a_profile_is_and_what_the_map_found(self, repo_root, upstream_built_dir, capsys):
        # given: the Cliopatria and Pleiades samples, where Aswan's granite quarry, worked by 1086 BCE, is inside Middle
        # Kingdom Egypt's area but not known to be worked by 1650 BCE
        assert main(["--root", str(repo_root), "--build-dir", str(upstream_built_dir), "explore", "--profile", "middle-kingdom-egypt"]) == 0
        out = capsys.readouterr().out
        assert "From the map: Middle Kingdom of Egypt (Cliopatria v0.2.2), 2050 BC to 1650 BC" in out
        granite = next(line for line in out.splitlines() if "Granite outcrop:" in line)
        assert granite.split()[0] == "maybe" and "(listed)" in granite

    def test_explore_json_says_what_the_map_found(self, repo_root, upstream_built_dir, capsys):
        args = ["--root", str(repo_root), "--build-dir", str(upstream_built_dir), "explore", "--profile", "middle-kingdom-egypt", "--json"]
        assert main(args) == 0
        result = json.loads(capsys.readouterr().out)
        assert result["place"]["cliopatria"] == "Middle Kingdom of Egypt"
        assert result["from_map"] == []  # nothing inside was worked by 1650 BCE, in the samples

    def test_deselect_removes_profile_items(self, repo_root, built_dir, capsys):
        main(["--root", str(repo_root), "--build-dir", str(built_dir), "explore", "--profile", "middle-kingdom-egypt", "--deselect", "copper-saw", "--json"])
        assert "copper-saw" not in json.loads(capsys.readouterr().out)["selected"]

    def test_check_job(self, repo_root, built_dir, capsys):
        assert main(["--root", str(repo_root), "--build-dir", str(built_dir), "check", "granite-slab-saw-cut", "--profile", "middle-kingdom-egypt"]) == 0
        assert "500–1,667 hours" in capsys.readouterr().out

    def test_build_reports_nodes_and_occurrences_separately(self, repo_root, tmp_path, capsys):
        assert main(["--root", str(repo_root), "--build-dir", str(tmp_path / "build"), "build"]) == 0
        output = capsys.readouterr().out
        # Nothing has been downloaded into a new build directory, so the cold backups are used.
        assert " source occurrences and " in output and " items to curate, from inputs " in output
        assert "mrds_deposits (backup of 2026-11-22)" in output

    @pytest.mark.parametrize(
        "args",
        [
            ["need", "unobtainium"],
            ["explore", "--profile", "atlantis"],
            ["explore", "--select", "unobtainium"],
            ["check", "no-such-job"],
        ],
    )
    def test_bad_input_exits_with_usage_error(self, repo_root, built_dir, capsys, args):
        assert main(["--root", str(repo_root), "--build-dir", str(built_dir), *args]) == 2
        assert "error:" in capsys.readouterr().err
