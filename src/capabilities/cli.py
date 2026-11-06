"""Command-line interface: `capabilities <command>`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from .graph import Graph, LoadError, find_root
from .reasoner import Backward, Selection, assess_job, closure, explore, need_tree
from .validate import validate


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        root = Path(args.root).resolve() if args.root else find_root()
        return args.handler(args, root)
    except (LoadError, UsageError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


class UsageError(Exception):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="capabilities", description="Query the Capabilities knowledge graph.")
    parser.add_argument("--root", help="Repository root holding schema/ and data/ (default: search upward from here).")
    commands = parser.add_subparsers(dest="command", required=True)

    cmd = commands.add_parser("validate", help="Check every data file against the schemas and cross-references.")
    cmd.add_argument("--quiet", action="store_true", help="Hide warnings; show errors only.")
    cmd.set_defaults(handler=cmd_validate)

    cmd = commands.add_parser("need", help="Q1: what would it take to make a thing or do an action (e.g. steel, cut:granite)?")
    cmd.add_argument("node")
    cmd.add_argument("--depth", type=int, default=12, help="Maximum tree depth (default 12).")
    cmd.add_argument("--json", action="store_true")
    cmd.set_defaults(handler=cmd_need)

    cmd = commands.add_parser("explore", help="Q2: given what a group made or did, what else was within reach?")
    add_selection_args(cmd)
    cmd.add_argument("--json", action="store_true")
    cmd.set_defaults(handler=cmd_explore)

    cmd = commands.add_parser("check", help="Q3: could a job be done, how long would it take, how precise could it be?")
    cmd.add_argument("job", help="A job id from examples/jobs, or a path to a job YAML file.")
    add_selection_args(cmd)
    cmd.add_argument("--json", action="store_true")
    cmd.set_defaults(handler=cmd_check)

    cmd = commands.add_parser("serve", help="Run the local API server.")
    cmd.add_argument("--host", default="127.0.0.1")
    cmd.add_argument("--port", type=int, default=8000)
    cmd.set_defaults(handler=cmd_serve)
    return parser


def add_selection_args(cmd: argparse.ArgumentParser) -> None:
    cmd.add_argument("--profile", help="Start from a profile, e.g. middle-kingdom-egypt.")
    cmd.add_argument("--select", nargs="*", default=[], metavar="ITEM",
                     help="Things made or had, or actions done (verb:target).")
    cmd.add_argument("--deselect", nargs="*", default=[], metavar="ITEM", help="Remove items from the profile.")
    cmd.add_argument("--hypothetical", nargs="*", default=[], metavar="ITEM", help="What-if additions, shown separately.")


def build_selection(graph: Graph, profile: str | None, select: list[str], deselect: list[str], hypothetical: list[str]) -> tuple[Selection, Selection]:
    selected = Selection()
    if profile:
        if profile not in graph.profiles:
            raise UsageError(f"unknown profile {profile!r}. Known: {', '.join(sorted(graph.profiles))}")
        selected = Selection.from_profile(graph.profiles[profile])
    selected = (selected | Selection.parse(select)) - Selection.parse(deselect)
    what_if = Selection.parse(hypothetical)
    unknown = (selected | what_if).unknown_ids(graph)
    if unknown:
        raise UsageError(f"unknown items: {', '.join(unknown)}")
    return selected, what_if


# ====================================================================== commands


def cmd_validate(args, root: Path) -> int:
    issues = validate(root)
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    for issue in errors + ([] if args.quiet else warnings):
        print(issue)
    print(f"\n{len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


def cmd_need(args, root: Path) -> int:
    graph = Graph.load(root)
    node = args.node
    if ":" in node:
        verb, target = node.split(":", 1)
        if verb not in graph.verbs or target not in graph.things:
            raise UsageError(f"unknown action {node!r}")
        certain = Backward(graph).of_action(verb, target)
    else:
        if graph.kind(node) not in ("material", "artifact"):
            raise UsageError(f"{node!r} is not a known material or artifact")
        certain = Backward(graph).of_thing(node)
    tree = need_tree(graph, node, args.depth)
    if args.json:
        print(json.dumps({"tree": tree, "certain": certain.to_dict(graph)}, indent=2, ensure_ascii=False))
        return 0
    print(f"What it would take: {tree['label']}\n")
    print_tree(tree)
    print("\nNeeded by every route (certain for anyone who had it):")
    print_necessity(certain.to_dict(graph))
    return 0


def cmd_explore(args, root: Path) -> int:
    graph = Graph.load(root)
    selected, what_if = build_selection(graph, args.profile, args.select, args.deselect, args.hypothetical)
    result = explore(graph, selected, what_if).to_dict(graph)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    section("Selected (confirmed made or done)", result["selected"])
    if result["hypothetical"]:
        section("Hypothetical (what-if)", result["hypothetical"])
    print("Implied (needed by every route to something selected):")
    print_necessity(result["implied"])
    print()
    section("Reachable (within reach, not selected)", result["reachable"])
    if result["maybe"]:
        section("Maybe reachable (depends on uncertain values)", result["maybe"])
    print("Actions within reach:")
    for verb, targets in result["actions"].items():
        yes = [t for t, s in targets.items() if s == "yes"]
        maybe = [t for t, s in targets.items() if s == "maybe"]
        line = f"  {verb}: {', '.join(yes) or '-'}"
        if maybe:
            line += f"  (maybe: {', '.join(maybe)})"
        print(line)
    print()
    print("One step away (one more raw ingredient):")
    for miss in result["near_misses"] or [{"thing": "-", "route": "", "missing": ""}]:
        print(f"  {miss['thing']}" + (f" via {miss['route']}: add {miss['missing']}" if miss["route"] else ""))
    if result["warnings"]:
        print()
        section("Warnings", result["warnings"])
    return 0


def cmd_check(args, root: Path) -> int:
    graph = Graph.load(root)
    job = load_job(graph, args.job)
    selected, what_if = build_selection(graph, args.profile, args.select, args.deselect, args.hypothetical)
    _, reach = closure(graph, selected, what_if)
    result = assess_job(graph, job, reach).to_dict()
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    print(f"Job: {job.get('label', job.get('id'))}")
    print(f"Verdict: {result['verdict'].upper()}")
    if result["total_hours"]:
        low, high = result["total_hours"]
        print(f"Total working time: {hours_text(low, high)} ({' to '.join(dict.fromkeys(b for b in result['total_bands'] if b))})")
    for reason in result["reasons"]:
        print(f"  - {reason}")
    for step in result["steps"]:
        print(f"\n{step['label']} ({step['verb']} {step['target']}), best route: {step['best'] or 'none'}")
        for route in step["routes"]:
            line = f"  {route['route']:26} {route['verdict']}"
            if route["hours"]:
                low, high = route["hours"]
                bands = " to ".join(dict.fromkeys(b for b in route["duration_bands"] if b))
                line += f" | {hours_text(low, high)} ({bands}) with {route['units']} working at once"
            if route["precision"]:
                line += f" | precision {route['precision']}"
            print(line)
            for reason in route["reasons"]:
                print(f"      - {reason}")
    return 0


def cmd_serve(args, root: Path) -> int:
    import uvicorn

    from .server import create_app

    uvicorn.run(create_app(root), host=args.host, port=args.port)
    return 0


# ====================================================================== helpers


def load_job(graph: Graph, ref: str) -> dict:
    if ref in graph.jobs:
        return graph.jobs[ref]
    path = Path(ref)
    if path.is_file():
        job = yaml.safe_load(path.read_text(encoding="utf-8"))
        job.setdefault("id", path.stem)
        return job
    raise UsageError(f"unknown job {ref!r}. Known: {', '.join(sorted(graph.jobs))}")


def hours_text(low: float, high: float) -> str:
    return f"{low:,.0f} hours" if round(low) == round(high) else f"{low:,.0f}–{high:,.0f} hours"


def section(title: str, items: list[str]) -> None:
    print(f"{title}:")
    for item in items or ["-"]:
        print(f"  {item}")
    print()


def print_necessity(necessity: dict) -> None:
    rows = [
        ("Things", necessity["things"]),
        ("Any of category", necessity["categories"]),
        ("Actions", necessity["actions"]),
        ("Techniques", necessity["techniques"]),
        ("Effects", [f"{effect}: {', '.join(f'{q} {b}' for q, b in bounds.items())}" for effect, bounds in necessity["effects"].items()]),
    ]
    for title, items in rows:
        if items:
            print(f"  {title}: {', '.join(items)}")


def print_tree(node: dict, indent: int = 0) -> None:
    pad = "  " * indent
    text = f"{pad}{node.get('role', '') + ' ' if node.get('role') else ''}{node['id']}"
    if node.get("natural"):
        text += f"  [natural, {node['natural']}]"
    if node.get("members"):
        text += f"  (any of: {', '.join(node['members'])})"
    if node.get("where"):
        text += f"  [{'; '.join(node['where'])}]"
    if node.get("too_weak"):
        text += f"  (too weak: {', '.join(node['too_weak'])})"
    if node.get("repeat"):
        text += "  (see above)"
    if node.get("truncated"):
        text += "  (...)"
    print(text)
    routes = node.get("routes", [])
    for route in routes:
        techniques = f"  [{', '.join(route['techniques'])}]" if route["techniques"] else ""
        print(f"{pad}  {'OR ' if len(routes) > 1 else ''}via {route['id']}{techniques}")
        for requirement in route["requires"]:
            print_tree(requirement, indent + 2)


if __name__ == "__main__":
    sys.exit(main())
