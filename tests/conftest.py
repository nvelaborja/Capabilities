import shutil
from pathlib import Path

import pytest

from capabilities.graph import Graph

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def graph() -> Graph:
    return Graph.load(REPO_ROOT)


@pytest.fixture
def data_copy(tmp_path: Path) -> Path:
    """A throwaway copy of the schemas and data, for tests that break files on purpose."""
    for directory in ("schema", "data", "examples"):
        shutil.copytree(REPO_ROOT / directory, tmp_path / directory)
    return tmp_path
