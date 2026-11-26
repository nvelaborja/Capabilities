"""Withdrawing a fact an agent proposed (ADR 0035, ADR 0050): taking it out of the curated layer, and recording why in
data/withdrawals.csv.

Three kinds of agent fact can be withdrawn: an ore crosswalk row (ADR 0048), a reference an agent added to a route, and
a quote an agent added to a person's reference (ADR 0049). A fact is removed entirely; the withdrawals file keeps what
it said (its quote, citation, URL and run), so the record survives, agents don't propose the same quote for the same
subject again, and validate refuses it if it comes back. A person's own fact is corrected by editing it: nothing here
touches one.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import yaml

from . import yaml_edit
from .graph import ORE_CROSSWALK, load_documents

WITHDRAWALS = Path("data") / "withdrawals.csv"
AGENT_RUNS = Path("data") / "agent_runs"
KINDS = ("ore_row", "reference", "quote")


class WithdrawError(Exception):
    """The fact can't be withdrawn: it isn't there, or no agent proposed it."""


@dataclass(frozen=True)
class Withdrawal:
    withdrawn_on: str
    kind: str  # ore_row, reference (an agent's whole reference) or quote (an agent's quote on a person's reference)
    subject: str  # the mineral (as MRDS names it) or the route id
    citation: str
    url: str
    quote: str
    run: str  # the agent run that proposed it
    reason: str
    report: str  # the GitHub issue that reported it, if one did


COLUMNS = tuple(Withdrawal.__dataclass_fields__)


def withdraw_ore_row(root: Path, mineral: str, reason: str, report: str = "", on: date | None = None) -> Withdrawal:
    """Take an agent's row for `mineral` (its MRDS name) out of the ore crosswalk. The mineral goes back to the queue."""
    path = root / ORE_CROSSWALK
    text = path.read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    found = [row for row in rows if row["mrds_ore"].casefold() == mineral.strip().casefold()]
    if not found:
        raise WithdrawError(f"the ore crosswalk has no row for {mineral!r}")
    row = found[0]
    if not row.get("proposed_by"):
        raise WithdrawError(f"{row['mrds_ore']}'s row wasn't proposed by an agent: correct it by editing "
                            f"{ORE_CROSSWALK}")
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=reader.fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(r for r in rows if r is not row)
    path.write_text(out.getvalue(), encoding="utf-8")
    return _record(root, Withdrawal(_day(on), "ore_row", row["mrds_ore"], row["citation"], row["url"], row["quote"],
                                    row["proposed_by"], reason, report))


def withdraw_reference(root: Path, route_id: str, citation: str, reason: str, report: str = "",
                       on: date | None = None) -> Withdrawal:
    """Take what an agent added to a route's reference citing `citation` out of the route's file: the whole reference
    if the agent added it, or the quote (and the URL it brought) if a person's reference was quoted."""
    path = _route_path(root, route_id)
    text = path.read_text(encoding="utf-8")
    try:
        index = yaml_edit.reference_citing(text, citation)
    except yaml_edit.EditError as error:
        raise WithdrawError(f"{route_id}: {error}") from error
    reference = yaml.safe_load(text)["references"][index]
    run = reference.get("proposed_by")
    if not run:
        raise WithdrawError(f"{route_id}'s reference to {citation!r} wasn't proposed by an agent: correct it by "
                            f"editing {path.relative_to(root)}")
    change = change_in_run(root, run, route_id, reference["citation"])
    if change["reference"] is None:
        kind, edited = "reference", yaml_edit.remove_reference(text, index)
    else:
        added = ("quote", "proposed_by") + (("url",) if change.get("adds_url") else ())
        kind, edited = "quote", yaml_edit.remove_fields(text, index, added)
    path.write_text(edited, encoding="utf-8")
    return _record(root, Withdrawal(_day(on), kind, route_id, reference["citation"], reference.get("url", ""),
                                    reference.get("quote", ""), run, reason, report))


def withdrawals(root: Path) -> list[dict]:
    path = root / WITHDRAWALS
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def withdrawn_quotes(root: Path) -> set[tuple[str, str]]:
    """Each withdrawn fact as (its subject, its quote), compared without case or spacing: what mustn't come back."""
    return {quote_key(row["subject"], row["quote"]) for row in withdrawals(root) if row["quote"].strip()}


def quote_key(subject: str, quote: str) -> tuple[str, str]:
    return subject.strip().casefold(), " ".join(quote.split()).casefold()


def _route_path(root: Path, route_id: str) -> Path:
    for document in load_documents(root)[0]:
        if document.data.get("kind") == "route" and document.data.get("id") == route_id:
            return document.path
    raise WithdrawError(f"no route {route_id!r}")


def change_in_run(root: Path, run: str, route_id: str, citation: str) -> dict:
    """What run `run` changed on the route's reference, from the summary its pull request committed: whether it added
    the reference or quoted a person's, and whether it gave the reference its URL."""
    path = root / AGENT_RUNS / f"{run}.json"
    if not path.is_file():
        raise WithdrawError(f"run {run}'s summary isn't in {AGENT_RUNS}: can't tell what it added to the reference")
    for item in json.loads(path.read_text(encoding="utf-8"))["items"]:
        change = item.get("change") or {}
        if change.get("route") == route_id and change.get("citation", "").strip() == citation.strip():
            return change
    raise WithdrawError(f"run {run}'s summary has no change to {route_id}'s reference to {citation!r}")


def _record(root: Path, withdrawal: Withdrawal) -> Withdrawal:
    path = root / WITHDRAWALS
    new = not path.is_file()
    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS, lineterminator="\n")
        if new:
            writer.writeheader()
        writer.writerow(asdict(withdrawal))
    return withdrawal


def _day(on: date | None) -> str:
    return (on or date.today()).isoformat()
