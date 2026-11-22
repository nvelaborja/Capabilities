import csv
import zipfile
from pathlib import Path

import pytest

# Fourteen real MRDS records (US public domain), picked to cover every rule in data/crosswalks/mrds_sources.csv.
SAMPLE = Path(__file__).parent / "fixtures" / "mrds-sample.csv"


def _mrds_zip(directory: Path, rows: list[dict] | None = None, columns: list[str] | None = None) -> str:
    """A zip shaped like USGS's mrds-csv.zip, holding the sample or the given rows, as a file:// URL."""
    with SAMPLE.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        rows = rows if rows is not None else list(reader)
        columns = columns or reader.fieldnames
    directory.mkdir(parents=True, exist_ok=True)
    data = directory / "mrds.csv"
    with data.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    archive = directory / "mrds-csv.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.write(data, "mrds.csv")
    return archive.as_uri()


def _sample_rows() -> list[dict]:
    with SAMPLE.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


@pytest.fixture(scope="session")
def mrds_zip():
    """Makes a zip shaped like USGS's mrds-csv.zip from the sample (or given rows), and returns it as a file:// URL."""
    return _mrds_zip


@pytest.fixture(scope="session")
def sample_rows():
    """Returns the sample's rows, as dictionaries, to change before zipping."""
    return _sample_rows
