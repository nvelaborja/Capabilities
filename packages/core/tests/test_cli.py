import json

import pytest

from capabilities.cli import main


class TestCli:
    def test_validate_passes_on_repository_data(self, repo_root, capsys):
        assert main(["--root", str(repo_root), "validate", "--quiet"]) == 0
        assert "0 errors" in capsys.readouterr().out

    def test_need_prints_tree_and_certain_needs(self, repo_root, capsys):
        assert main(["--root", str(repo_root), "need", "steel"]) == 0
        out = capsys.readouterr().out
        assert "via steel-by-carburizing" in out
        assert "heat: duration_h >= 24, temperature_c >= 1100" in out

    def test_explore_json(self, repo_root, capsys):
        assert main(["--root", str(repo_root), "explore", "--profile", "middle-kingdom-egypt", "--hypothetical", "hematite", "--json"]) == 0
        result = json.loads(capsys.readouterr().out)
        assert "steel" in result["reachable"]
        assert result["hypothetical"] == ["hematite"]

    def test_deselect_removes_profile_items(self, repo_root, capsys):
        main(["--root", str(repo_root), "explore", "--profile", "middle-kingdom-egypt", "--deselect", "copper-saw", "--json"])
        assert "copper-saw" not in json.loads(capsys.readouterr().out)["selected"]

    def test_check_job(self, repo_root, capsys):
        assert main(["--root", str(repo_root), "check", "granite-slab-saw-cut", "--profile", "middle-kingdom-egypt"]) == 0
        assert "500–1,667 hours" in capsys.readouterr().out

    @pytest.mark.parametrize(
        "args",
        [
            ["need", "unobtainium"],
            ["explore", "--profile", "atlantis"],
            ["explore", "--select", "unobtainium"],
            ["check", "no-such-job"],
        ],
    )
    def test_bad_input_exits_with_usage_error(self, repo_root, capsys, args):
        assert main(["--root", str(repo_root), *args]) == 2
        assert "error:" in capsys.readouterr().err
