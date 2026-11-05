"""Local server: the web UI at /, the API under /api, and interactive API docs at /docs.

Run with `capabilities serve`. The web UI is served from web/dist, which `npm run build` creates in web/.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .graph import Graph, find_root
from .levels import compute_levels
from .reasoner import Backward, Selection, assess_job, closure, explore, need_tree
from .views import StatusContext, UnknownNode, explain, explore_view, graph_view, parse_action


class SelectionRequest(BaseModel):
    profile: str | None = Field(None, description="Start from a profile, e.g. middle-kingdom-egypt.")
    select: list[str] = Field(default_factory=list, description="Things they made or had, or actions they did (verb:target).")
    deselect: list[str] = Field(default_factory=list, description="Items to remove from the profile.")
    hypothetical: list[str] = Field(default_factory=list, description="What-if additions, reported separately.")


class ExplainRequest(SelectionRequest):
    node: str = Field(..., description="A thing, category or effect id, or an action (verb:target).")
    all: bool = Field(False, description="Also list every certain need at every depth (\"Expand all dependencies\").")


class CheckRequest(SelectionRequest):
    job: str | None = Field(None, description="A job id from examples/jobs.")
    job_spec: dict | None = Field(None, description="An inline job, in the same shape as a job YAML file.")


UNBUILT_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Capabilities</title>
<style>body{font:16px/1.5 system-ui,sans-serif;max-width:40rem;margin:4rem auto;padding:0 1rem}code{font-size:.9em}</style>
</head><body>
<h1>Capabilities</h1>
<p>The API is running, but the web app hasn't been built yet. Build it once (you need <a href="https://nodejs.org/">Node.js</a>):</p>
<pre><code>cd web
npm ci
npm run build</code></pre>
<p>Then reload this page. Meanwhile, the API docs are at <a href="/docs">/docs</a>.</p>
</body></html>
"""


def create_app(root: Path | None = None, web_dist: Path | None = None) -> FastAPI:
    root = root or find_root()
    graph = Graph.load(root)
    levels = compute_levels(graph)
    api = APIRouter(prefix="/api")
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

    @api.get("/health")
    def health() -> dict:
        return {"status": "ok", "things": len(graph.things), "routes": len(graph.routes)}

    @api.get("/nodes")
    def nodes(kind: str | None = Query(None, description="Filter by kind, e.g. material, artifact, route, verb.")) -> list[dict]:
        everything = [
            *({"id": i, "kind": t["kind"], "label": t["label"]} for i, t in graph.things.items()),
            *({"id": i, "kind": "verb", "label": v["label"]} for i, v in graph.verbs.items()),
            *({"id": i, "kind": "route", "label": r["label"]} for i, r in graph.routes.items()),
        ]
        return sorted((n for n in everything if kind is None or n["kind"] == kind), key=lambda n: n["id"])

    @api.get("/nodes/{node_id}")
    def node(node_id: str) -> dict:
        for bucket in (graph.things, graph.verbs, graph.routes):
            if node_id in bucket:
                used_by = sorted(
                    rid for rid, route in graph.routes.items()
                    if any(node_id in (r.get("thing"), r.get("category"), r.get("effect"), r.get("verb")) for r in route["requires"])
                )
                return {"node": bucket[node_id], "made_by": graph.routes_achieving.get(node_id, []), "used_by": used_by}
        raise HTTPException(404, f"Unknown node {node_id!r}")

    @api.get("/profiles")
    def profiles() -> list[dict]:
        return [
            {"id": i, "label": p["label"], "period": p.get("period"), "region": p.get("region"), "description": p.get("description")}
            for i, p in sorted(graph.profiles.items())
        ]

    @api.get("/profiles/{profile_id}")
    def profile(profile_id: str) -> dict:
        if profile_id not in graph.profiles:
            raise HTTPException(404, f"Unknown profile {profile_id!r}")
        return graph.profiles[profile_id]

    @api.get("/jobs")
    def jobs() -> list[dict]:
        return [{"id": i, "label": j["label"]} for i, j in sorted(graph.jobs.items())]

    @api.get("/need/{node}")
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

    @api.get("/graph")
    def graph_endpoint(action: list[str] = Query(default_factory=list, description="Extra actions to draw, e.g. cut:limestone.")) -> dict:
        """Every drawable node and edge, with tech levels. Routes are junction nodes between a thing and its requirements."""
        extra = []
        for key in action:
            if ":" not in key or Selection.parse([key]).unknown_ids(graph):
                raise HTTPException(422, f"Unknown action {key!r}; expected verb:target, e.g. cut:limestone")
            extra.append(parse_action(key))
        return graph_view(graph, levels, extra)

    @api.post("/explore")
    def explore_endpoint(request: SelectionRequest) -> dict:
        """Q2: given what a group made or did, what else was within reach? Includes a status for every drawable node."""
        selected, what_if = selection(request)
        return explore_view(graph, explore(graph, selected, what_if))

    @api.post("/explain")
    def explain_endpoint(request: ExplainRequest) -> dict:
        """A node's first-degree requirements, each met / missing / unknown with a reason, given a selection."""
        selected, what_if = selection(request)
        context = StatusContext.from_explore(graph, explore(graph, selected, what_if))
        try:
            return explain(graph, levels, context, request.node, everything=request.all)
        except UnknownNode:
            raise HTTPException(404, f"{request.node!r} is not a thing, category, effect or action that can be explained") from None

    @api.post("/check")
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

    app.include_router(api)
    _serve_web(app, web_dist or root / "web" / "dist")
    return app


def _serve_web(app: FastAPI, dist: Path) -> None:
    """Serve the built web UI at the root, after the API routes so /api and /docs keep priority."""
    if (dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
        return

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def unbuilt() -> str:
        return UNBUILT_PAGE
