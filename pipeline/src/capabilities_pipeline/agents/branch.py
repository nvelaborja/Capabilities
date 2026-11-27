"""Where accepted proposals go: a temporary worktree on a new branch, `agents/<run>`, started from main (ADR 0048).

There the changes are written (crosswalk rows, a route's references), and the checks that need the whole repository
run: Wikidata's labels and quantities for the new items and OpenAlex and Crossref for the new citations are downloaded,
and the graph is built, its tests and all. A change whose cited work is wrong is dropped, and the rest are checked
again. What passes is
committed with the refreshed cold backups, the works cited and the run's summary, pushed, and opened as a draft pull
request with the user's own `gh` login. The run never merges: the pull request is the review (ADR 0035).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

import duckdb
from capabilities.built import CHECKS_FILE, graph_dir
from capabilities.validate import validate

from ..build import BuildError, build
from ..upstream import REFERENCES, WIKIDATA, WIKIDATA_ITEMS, back_up, fetch
from .task import Check

log = logging.getLogger(__name__)

RUNS_DIR = Path("data") / "agent_runs"
# What a build sets in the environment for dbt (build.dbt_environment).
DBT_ENVIRONMENT = ("CAPABILITIES_BUILD_DIR", "DBT_LOG_PATH", "DBT_TARGET_PATH", "DO_NOT_TRACK")
# What the citation check can say that makes a row wrong: the DOI it cites leads to another work. Anything else (found,
# possible, not found, not searched) is noted, not held against it: the row's own page was downloaded and the quote
# found on it, and many books, reports and web pages are in neither index (ADR 0047, ADR 0048).
WRONG = ("doi_disagrees",)


class BranchError(Exception):
    """git or gh failed."""


@dataclass(frozen=True)
class Proposals:
    """What a run's proposals are published as: the pull request's title and body, and the commit's subject."""

    title: str
    body: str
    commit: str  # a conventional commit, as every commit in the repository is
    files: tuple[Path, ...]  # what the changes wrote, relative to the repository


@dataclass(frozen=True)
class Downloads:
    """Where the gate downloads from: the same services the build's upstream assets use."""

    wikidata_url: str = WIKIDATA.url  # the SPARQL endpoint
    openalex_url: str = REFERENCES.url
    crossref_url: str = REFERENCES.crossref_url
    wikidata_site_url: str = "https://www.wikidata.org"  # items and search, for finding a mineral's item


class Worktree:
    """A temporary worktree of the repository on a new branch. Removed on exit, with the branch unless it was pushed."""

    def __init__(self, repo: Path, branch: str, base: str, directory: Path):
        self.repo, self.branch, self.base, self.root = repo, branch, base, directory
        self.pushed = False

    def __enter__(self) -> Worktree:
        if self.base.startswith("origin/"):
            git(self.repo, "fetch", "origin", self.base.removeprefix("origin/"))
        git(self.repo, "worktree", "add", "-b", self.branch, str(self.root), self.base)
        return self

    def __exit__(self, *exc) -> None:
        # Cleaning up mustn't fail the run, nor hide the error that ended it: a leftover is only warned about.
        try:
            self._remove()
        except BranchError as error:
            log.warning("Couldn't remove the worktree %s: %s", self.root, error)
        if not self.pushed:
            try:
                git(self.repo, "branch", "-D", self.branch)
            except BranchError as error:
                log.warning("Couldn't delete the branch %s: %s", self.branch, error)

    def _remove(self) -> None:
        try:
            git(self.repo, "worktree", "remove", "--force", str(self.root))
        except BranchError:
            shutil.rmtree(self.root, ignore_errors=True)
            git(self.repo, "worktree", "prune")

    def restore(self, files: list[Path]) -> None:
        """The files as the branch has them, before the next set of changes is written."""
        git(self.root, "checkout", "--", *map(str, files))


def git(directory: Path, *arguments: str) -> str:
    return run_command(["git", "-C", str(directory), *arguments])


def run_command(command: list[str], cwd: Path | None = None) -> str:
    try:
        return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=True, timeout=300).stdout.strip()
    except subprocess.CalledProcessError as error:
        raise BranchError(f"`{' '.join(command[:4])}…` failed: {(error.stderr or error.stdout).strip()}") from error
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BranchError(f"couldn't run {command[0]}: {error}") from error


def check_gh(gh: str = "gh") -> None:
    """That `gh` is logged in, before a run spends any usage on proposals it couldn't open a pull request for."""
    run_command([gh, "auth", "status"])


def gate(root: Path, build_dir: Path, downloads: Downloads) -> dict[str, dict]:
    """Validate the data, download what the changes need, and build the graph from `root`, as a person adding them
    would. Returns the citation checks by citation. Data that doesn't validate, or a build that fails, raises
    BuildError."""
    if errors := [str(issue) for issue in validate(root) if issue.severity == "error"]:
        raise BuildError("the data doesn't validate: " + "; ".join(errors))
    fetch(WIKIDATA, build_dir, downloads.wikidata_url, root=root)
    fetch(WIKIDATA_ITEMS, build_dir, downloads.wikidata_url, root=root)
    fetch(replace(REFERENCES, crossref_url=downloads.crossref_url), build_dir, downloads.openalex_url, root=root)
    # A build points dbt at its build directory through the environment; the repository's own build keeps its own.
    saved = {name: os.environ.get(name) for name in DBT_ENVIRONMENT}
    try:
        build(root, build_dir)
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    rows = duckdb.sql(
        "select citation, result, note, match_service, links::varchar from read_parquet(?)",
        params=[str(graph_dir(build_dir) / CHECKS_FILE)],
    ).fetchall()
    return {citation: {"result": result, "note": note, "match_service": service, "links": json.loads(links or "[]")}
            for citation, result, note, service, links in rows}


def work_check(citation: str | None, checks: dict[str, dict]) -> Check:
    """Whether the build's citation check found anything wrong with the work a change cites; None for a change whose
    citation isn't looked up (a rejected mineral's row builds nothing)."""
    if citation is None:
        return Check("citation_check_passes", True, "not looked up: a rejected mineral's reference builds nothing")
    found = checks.get(citation)
    if found is None:
        return Check("citation_check_passes", False, "the citation wasn't checked")
    result, service = found["result"], found["match_service"]
    if result in WRONG:
        return Check("citation_check_passes", False, f"{result}: {found['note']}")
    where = f" in {'OpenAlex' if service == 'openalex' else 'Crossref'}" if service else ""
    return Check("citation_check_passes", True, f"{result}{where}; its page loaded and the quote is on it")


def publish(worktree: Worktree, build_dir: Path, run_id: str, summary: dict, proposals: Proposals, gh: str) -> str:
    """Commit the changes with what goes with them, push the branch, and open a draft pull request. Returns its URL."""
    root = worktree.root
    for dataset in (WIKIDATA, WIKIDATA_ITEMS, REFERENCES):
        back_up(dataset, root, build_dir)
    _refresh_credits(root)
    path = root / RUNS_DIR / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    git(root, "add", "--", *map(str, proposals.files), str(RUNS_DIR), "snapshots", "CREDITS.md")
    git(root, "commit", "-m", proposals.commit, "-m", f"Run summary: {RUNS_DIR / f'{run_id}.json'}. Every reference is "
        "unverified until a person reads it.")
    git(root, "push", "-u", "origin", worktree.branch)
    worktree.pushed = True
    body_file = build_dir / "pull-request.md"
    body_file.write_text(proposals.body, encoding="utf-8")
    return run_command([gh, "pr", "create", "--draft", "--base", worktree.base.removeprefix("origin/"), "--head",
                 worktree.branch, "--title", proposals.title, "--body-file", str(body_file)], cwd=root).splitlines()[-1]


def _refresh_credits(root: Path) -> None:
    from capabilities.cli import main

    if main(["--root", str(root), "credits"]) != 0:
        raise BranchError("couldn't regenerate the works cited in CREDITS.md")
