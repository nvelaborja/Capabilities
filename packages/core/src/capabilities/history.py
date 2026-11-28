"""Comparing the graph with history (ADR 0053): what Seshat records polities had, against what the graph can reach from
the sources the map gives each polity's area.

Each polity Seshat codes, with Cliopatria's borders for it, has a generated profile (ADR 0052): its area and years, and
only basic inputs, the sources worked inside the area by its last year. Nothing is hand-picked. The reasoner explores
from those, and each variable the crosswalk compares is one of:

    agree                   the graph reaches it and Seshat records it, or neither
    history_yes_graph_no    Seshat records it, the graph can't reach it from the area: the requirement that stops it is
                            named, and is a gap to look at (missing data, trade, or a wrong route)
    graph_yes_history_no    the graph reaches it, Seshat doesn't record it. Weaker: Seshat's metals are military use,
                            and not using a metal in war isn't not having it
    unknown                 Seshat doesn't know, or the graph's answer is maybe

Seshat's data is CC BY-SA 4.0: the comparison is written to the build only, never to data/.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .graph import Graph
from .reasoner import Backward, ExploreResult, Selection, explore
from .tristate import Tri

RESULTS_FILE = "backtest_results.parquet"
GAPS_FILE = "graph_gaps.parquet"
SUMMARY_FILE = "backtest.json"


@dataclass(frozen=True)
class Polity:
    """A generated profile: a Seshat polity, its years, and the sources the map gives its area."""

    id: str
    label: str
    polity: str
    years: tuple[int, int]
    had: frozenset[str]  # sources worked inside the area by the last year: the profile's selection
    found: frozenset[str]  # every source kind or ore class with a mapped place inside, worked by then or not
    worked: frozenset[str]  # those with one worked by then, ore classes included
    present: frozenset[str]  # sources with a mapped place there, worked by then or not: what it could have had (ADR 0036)


def load_polities(graph_dir: Path) -> dict[str, Polity]:
    """The generated profiles of a build, with what the map gives each."""
    import duckdb

    areas = duckdb.sql(
        "select id, label, seshat_polity, from_year, to_year from read_parquet(?) "
        "where id is not null and origin = 'seshat' order by id",
        params=[str(graph_dir / "profile_areas.parquet")],
    ).fetchall()
    sources: dict[str, list[tuple]] = defaultdict(list)
    for profile_id, source_id, kind, availability in duckdb.sql(
        "select profile_id, source_id, source_kind, availability from read_parquet(?) where id is not null",
        params=[str(graph_dir / "profile_sources.parquet")],
    ).fetchall():
        sources[profile_id].append((source_id, kind, availability))
    return {
        profile_id: Polity(
            id=profile_id,
            label=label,
            polity=polity,
            years=(first, last),
            had=frozenset(s for s, kind, availability in sources[profile_id] if availability == "yes" and kind == "source"),
            found=frozenset(s for s, _, _ in sources[profile_id]),
            worked=frozenset(s for s, _, availability in sources[profile_id] if availability == "yes"),
            present=frozenset(s for s, kind, _ in sources[profile_id] if kind == "source"),
        )
        for profile_id, label, polity, first, last in areas
    }


def load_codings(graph_dir: Path) -> list[dict]:
    """What Seshat says each polity had, one row per polity and compared variable."""
    import duckdb

    columns = ("profile_id", "polity_id", "seshat_polity", "variable", "compares", "thing", "history", "tags", "disputed",
               "records")
    rows = duckdb.sql(
        f"select {', '.join(columns)} from read_parquet(?) where id is not null order by profile_id, variable",
        params=[str(graph_dir / "history_codings.parquet")],
    ).fetchall()
    return [dict(zip(columns, row)) for row in rows]


def compare_with_history(graph: Graph, polities: dict[str, Polity], codings: list[dict]) -> list[dict]:
    """One row per polity and variable: what Seshat says, what the graph says, and how they compare."""
    reach = Reach(graph)
    explored = {profile_id: reach.explore(polity.had) for profile_id, polity in polities.items()}
    rows = []
    for coding in codings:
        polity = polities.get(coding["profile_id"])
        if polity is None:
            continue
        if coding["compares"] == "worked_source":
            answer, missing, reason = worked_source_answer(graph, polity)
        else:
            answer, missing, reason = thing_answer(graph, explored[polity.id], coding["thing"])
        cause = "absent" if answer == "no" else None
        if answer == "no" and coding["compares"] == "thing":
            cause, missing, reason = no_cause(reach, polity, coding["thing"])
        rows.append({
            **coding,
            "label": polity.label,
            "from_year": polity.years[0],
            "to_year": polity.years[1],
            "had": sorted(polity.had),
            "graph": answer,
            "outcome": outcome(coding["history"], answer),
            "missing": missing,
            "reason": reason,
            # For a no: `ore_unrecorded`, `undated` or `absent` (no_cause).
            "cause": cause,
        })
    return rows


class Reach:
    """The reasoner's answers for sets of sources, remembered: polities share source kinds, so the same sets recur."""

    def __init__(self, graph: Graph):
        self.graph = graph
        self.results: dict[frozenset[str], ExploreResult] = {}

    def explore(self, sources: frozenset[str]) -> ExploreResult:
        if sources not in self.results:
            self.results[sources] = explore(self.graph, Selection(sources))
        return self.results[sources]

    def reaches(self, sources: frozenset[str], thing: str) -> bool:
        return reached(self.explore(sources), thing)

    def expand(self, ids) -> frozenset[str]:
        """Sources, with each ore class as the sources of its minerals: what a mine of the class could have been."""
        return frozenset(source for i in ids for source in (
            class_sources(self.graph, i) if self.graph.kind(i) == "category" else (i,)))

    def needed(self, base: frozenset[str], candidates: list[str], thing: str) -> list[str]:
        """Of the candidates that, with the base, reach the thing: those it can't do without (copper and tin for bronze),
        or, when none is, those that would do on their own (any copper deposit)."""
        essential = [c for c in candidates
                     if not self.reaches(base | self.expand(other for other in candidates if other != c), thing)]
        return essential or [c for c in candidates if self.reaches(base | self.expand([c]), thing)] or candidates


def reached(result: ExploreResult, thing: str) -> bool:
    return thing in result.selected.things or result.reach.status.get(thing, Tri.NO) != Tri.NO


def no_cause(reach: Reach, polity: Polity, thing: str) -> tuple[str, list[str], str]:
    """Why the graph says no: the least it takes, widening what the polity had, to reach the thing.

    ore_unrecorded  the sources of ore classes with a mine worked in the area by then: which ore isn't recorded, so it
                    can't be selected (ADR 0046, ADR 0052)
    undated         every place mapped there, worked by then or not: a dated working would settle it (and, if a worked
                    mine of an ore class is needed too, which ore it yielded)
    absent          not even those: the area lacks a source, or the graph a route. What is named is what is still
                    missing with every place mapped there, not only those worked by then.
    """
    graph = reach.graph
    worked_classes = sorted(c for c in polity.worked - polity.had if graph.kind(c) == "category")
    undated_classes = sorted(c for c in polity.found - polity.worked if graph.kind(c) == "category")
    undated = sorted(polity.present - polity.had) + undated_classes
    with_ores = polity.had | reach.expand(worked_classes)
    everything = with_ores | reach.expand(undated)
    if not reach.reaches(everything, thing):
        _, missing, reason = thing_answer(graph, reach.explore(everything), thing)
        return "absent", missing, reason
    if worked_classes and reach.reaches(with_ores, thing):
        classes = reach.needed(polity.had, worked_classes, thing)
        return "ore_unrecorded", classes, ("a mine of " + ", ".join(graph.label(c).lower() for c in classes)
                                           + " was worked there by then, but which ore isn't recorded")
    dates = reach.needed(with_ores, undated, thing)
    # A worked ore-class mine the thing needs as well (copper from one, tin from an undated place).
    ores = [c for c in worked_classes if not reach.reaches(
        polity.had | reach.expand(other for other in worked_classes if other != c) | reach.expand(undated), thing)]
    reason = ("there, but none known to be worked by then: " + ", ".join(graph.label(s) for s in dates)
              + "; a dated working would settle it")
    if ores:
        reason += " (and which ore a worked mine of " + ", ".join(graph.label(c).lower() for c in ores) + " yielded)"
    return "undated", dates, reason


def thing_answer(graph: Graph, result: ExploreResult, thing: str) -> tuple[str, list[str], str]:
    """Whether the graph reaches the thing from the polity's sources, and if not, what stops it: the raw ingredients
    one of which would be enough (one step away, ADR 0027), else the needs every route to it shares that aren't met."""
    status = Tri.YES if thing in result.selected.things else result.reach.status.get(thing, Tri.NO)
    if status == Tri.YES:
        return "yes", [], "reachable from the sources worked in the area"
    if status == Tri.MAYBE:
        return "maybe", [], "reachable only if uncertain values allow it"
    one_step = sorted({miss["missing"] for miss in result.near_misses if miss["thing"] == thing})
    if one_step:
        return "no", one_step, "one of these would be enough: " + ", ".join(graph.label(t) for t in one_step)
    unmet = unmet_needs(graph, result, thing)
    if unmet:
        return "no", unmet, "every route needs " + ", ".join(graph.label(t) for t in unmet)
    return "no", [], "more than one ingredient is missing; see what it would take"


def unmet_needs(graph: Graph, result: ExploreResult, thing: str) -> list[str]:
    """What every route to the thing needs, things and kinds of thing, that the polity's sources don't reach."""
    needs = Backward(graph).of_thing(thing)
    things = [t for t in needs.things if not reached(result, t)]
    categories = [c for c in needs.categories if not any(reached(result, member) for member in graph.members(c))]
    return sorted(things + categories)


def class_sources(graph: Graph, category: str) -> frozenset[str]:
    """The sources of an ore class's minerals: what a mine of the class could have been."""
    return frozenset(source for member in graph.members(category) for source in graph.sources_of(member))




def worked_source_answer(graph: Graph, polity: Polity) -> tuple[str, list[str], str]:
    """Whether the map gives the polity's area a mine, quarry or deposit worked by its last year."""
    if polity.worked:
        return "yes", [], "worked there by then: " + ", ".join(graph.label(s) for s in sorted(polity.worked))
    if polity.found:
        return "maybe", [], "mapped there, none known to be worked by then"
    return "no", [], "no mapped mine, quarry or deposit in the area"


def outcome(history: str, graph: str) -> str:
    if history == "unknown" or graph == "maybe":
        return "unknown"
    if (history == "present") == (graph == "yes"):
        return "agree"
    return "history_yes_graph_no" if history == "present" else "graph_yes_history_no"


def graph_gaps(rows: list[dict], graph: Graph) -> list[dict]:
    """What history shows that the graph can't reach, the most polities first. A gap for want of a source or a route
    (`absent`) is grouped by what stops it, since that is what to fix; one for want of dates (`undated`) by the thing
    alone, since the fix is the same, a dated working, wherever it is."""
    grouped: dict[tuple[str, str, tuple[str, ...]], list[dict]] = defaultdict(list)
    for row in rows:
        if row["outcome"] == "history_yes_graph_no" and row["compares"] == "thing":
            missing = tuple(row["missing"]) if row["cause"] == "absent" else ()
            grouped[(row["thing"], row["cause"], missing)].append(row)
    gaps = [gap(graph, thing, cause, missing, group) for (thing, cause, missing), group in grouped.items()]
    return sorted(gaps, key=lambda item: (-item["polities"], item["id"]))


def gap(graph: Graph, thing: str, cause: str, missing: tuple[str, ...], group: list[dict]) -> dict:
    if cause in ("undated", "ore_unrecorded"):
        sources = sorted({source for row in group for source in row["missing"]})
        reason = ("each area has places that would do, none known to be worked by then (" +
                  ", ".join(graph.label(s) for s in sources) + "): dated workings would settle it"
                  if cause == "undated" else "a mine of an ore class was worked in each area by then (" +
                  ", ".join(graph.label(s).lower() for s in sources) + "), but which ore isn't recorded")
    else:
        sources, reason = list(missing), group[0]["reason"]
    return {
        # What is missing can be ten deposit kinds: the id keeps a short digest of it, and `missing` the list.
        "id": f"{thing}/{cause}" + (f"/{hashlib.sha1('+'.join(missing).encode()).hexdigest()[:8]}" if missing else ""),
        "thing": thing,
        "label": graph.label(thing),
        "cause": cause,
        "missing": sources,
        "reason": reason,
        "polities": len(group),
        "examples": sorted(row["label"] for row in group)[:10],
    }


def write_backtest(graph: Graph, graph_dir: Path, fingerprint: str | None) -> dict:
    """Run the comparison on a build, and write its results, gaps and summary beside the graph."""
    import duckdb

    rows = compare_with_history(graph, load_polities(graph_dir), load_codings(graph_dir))
    gaps = graph_gaps(rows, graph)
    write_rows(duckdb, rows, graph_dir / RESULTS_FILE, integers=("polity_id", "from_year", "to_year"))
    write_rows(duckdb, gaps, graph_dir / GAPS_FILE, integers=("polities",))
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row["outcome"]] += 1
    summary = {
        # The build it compared: a newer build makes these results stale.
        "fingerprint": fingerprint,
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "polities": len({row["profile_id"] for row in rows}),
        "comparisons": len(rows),
        "outcomes": dict(sorted(counts.items())),
        "gaps": len(gaps),
    }
    (graph_dir / SUMMARY_FILE).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def write_rows(duckdb, rows: list[dict], path: Path, integers: tuple[str, ...] = ()) -> None:
    """Rows as Parquet, through JSON so lists keep their types; an empty list of rows still makes a file. JSON readers
    can guess a number column is a double: `integers` are cast back."""
    scratch = path.with_suffix(".json")
    scratch.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    try:
        if rows:
            casts = ", ".join(f"{column}::bigint as {column}" for column in integers)
            select = f"select * replace ({casts})" if casts else "select *"
            duckdb.sql(f"copy ({select} from read_json_auto(?)) to '{path}' (format parquet)", params=[str(scratch)])
        else:
            duckdb.sql(f"copy (select null::varchar as id where false) to '{path}' (format parquet)")
    finally:
        scratch.unlink()


def load_results(graph_dir: Path) -> list[dict]:
    """The last comparison's rows, or none."""
    return read_rows(graph_dir / RESULTS_FILE)


def load_gaps(graph_dir: Path) -> list[dict]:
    return read_rows(graph_dir / GAPS_FILE)


def read_rows(path: Path) -> list[dict]:
    import duckdb

    if not path.is_file():
        return []
    relation = duckdb.read_parquet(str(path))
    return [dict(zip(relation.columns, row)) for row in relation.fetchall()]


def load_summary(graph_dir: Path) -> dict | None:
    path = graph_dir / SUMMARY_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
