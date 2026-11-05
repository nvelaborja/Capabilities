"""Local HTTP API. Run with `capabilities serve`, then open http://127.0.0.1:8000/docs for interactive docs."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from . import __version__
from .graph import Graph, find_root
from .reasoner import Backward, Selection, assess_job, closure, explore, need_tree


class SelectionRequest(BaseModel):
    profile: str | None = Field(None, description="Start from a profile, e.g. middle-kingdom-egypt.")
    select: list[str] = Field(default_factory=list, description="Things they made or had, or actions they did (verb:target).")
    deselect: list[str] = Field(default_factory=list, description="Items to remove from the profile.")
    hypothetical: list[str] = Field(default_factory=list, description="What-if additions, reported separately.")


class CheckRequest(SelectionRequest):
    job: str | None = Field(None, description="A job id from examples/jobs.")
    job_spec: dict | None = Field(None, description="An inline job, in the same shape as a job YAML file.")


def create_app(root: Path | None = None) -> FastAPI:
    graph = Graph.load(root or find_root())
    app = FastAPI(
        title="Capabilities",
        version=__version__,
        description="What would it take to make X? What else could they do? Could this job have been done this way?",
    )

    def selection(request: SelectionRequest) -> tuple[Selection, Selection]:
        selected = Selection()
        if request.profile:
            if request.profile not in graph.profiles:
                raise HTTPException(404, f"Unknown profile {request.profile!r}")
            selected = Selection.from_profile(graph.profiles[request.profile])
        selected = (selected | Selection.parse(request.select)) - Selection.parse(request.deselect)
        what_if = Selection.parse(request.hypothetical)
        unknown = (selected | what_if).unknown_ids(graph)
        if unknown:
            raise HTTPException(422, f"Unknown items: {', '.join(unknown)}")
        return selected, what_if

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "things": len(graph.things), "routes": len(graph.routes)}

    @app.get("/nodes")
    def nodes(kind: str | None = Query(None, description="Filter by kind, e.g. material, artifact, route, verb.")) -> list[dict]:
        everything = [
            *({"id": i, "kind": t["kind"], "label": t["label"]} for i, t in graph.things.items()),
            *({"id": i, "kind": "verb", "label": v["label"]} for i, v in graph.verbs.items()),
            *({"id": i, "kind": "route", "label": r["label"]} for i, r in graph.routes.items()),
        ]
        return sorted((n for n in everything if kind is None or n["kind"] == kind), key=lambda n: n["id"])

    @app.get("/nodes/{node_id}")
    def node(node_id: str) -> dict:
        for bucket in (graph.things, graph.verbs, graph.routes):
            if node_id in bucket:
                used_by = sorted(
                    rid for rid, route in graph.routes.items()
                    if any(node_id in (r.get("thing"), r.get("category"), r.get("effect"), r.get("verb")) for r in route["requires"])
                )
                return {"node": bucket[node_id], "made_by": graph.routes_achieving.get(node_id, []), "used_by": used_by}
        raise HTTPException(404, f"Unknown node {node_id!r}")

    @app.get("/profiles")
    def profiles() -> list[dict]:
        return [{"id": i, "label": p["label"], "period": p.get("period")} for i, p in sorted(graph.profiles.items())]

    @app.get("/profiles/{profile_id}")
    def profile(profile_id: str) -> dict:
        if profile_id not in graph.profiles:
            raise HTTPException(404, f"Unknown profile {profile_id!r}")
        return graph.profiles[profile_id]

    @app.get("/jobs")
    def jobs() -> list[dict]:
        return [{"id": i, "label": j["label"]} for i, j in sorted(graph.jobs.items())]

    @app.get("/need/{node}")
    def need(node: str, depth: int = 12) -> dict:
        """Q1: what would it take to make a thing, or do an action (e.g. `cut:granite`)?"""
        if ":" in node:
            verb, target = node.split(":", 1)
            if verb not in graph.verbs or target not in graph.things:
                raise HTTPException(404, f"Unknown action {node!r}")
            certain = Backward(graph).of_action(verb, target)
        elif graph.kind(node) in ("material", "artifact"):
            certain = Backward(graph).of_thing(node)
        else:
            raise HTTPException(404, f"{node!r} is not a known material or artifact")
        return {"tree": need_tree(graph, node, depth), "certain": certain.to_dict(graph)}

    @app.post("/explore")
    def explore_endpoint(request: SelectionRequest) -> dict:
        """Q2: given what a group made or did, what else was within reach?"""
        selected, what_if = selection(request)
        return explore(graph, selected, what_if).to_dict(graph)

    @app.post("/check")
    def check(request: CheckRequest) -> dict:
        """Q3: could a job be done with what is reachable, how long would it take, and how precise could it be?"""
        if request.job:
            if request.job not in graph.jobs:
                raise HTTPException(404, f"Unknown job {request.job!r}")
            job = graph.jobs[request.job]
        elif request.job_spec:
            job = {"id": "(inline job)", **request.job_spec}
        else:
            raise HTTPException(422, "Provide either job or job_spec.")
        selected, what_if = selection(request)
        _, reach = closure(graph, selected, what_if)
        return assess_job(graph, job, reach).to_dict()

    return app
