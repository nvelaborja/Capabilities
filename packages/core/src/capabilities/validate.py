"""Schema validation plus cross-file checks (ids, references, ranges) and evidence-gap warnings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from .graph import HELD_KINDS, THING_DIRS, Document, Graph, achieved_id, achieved_kind, load_documents


@dataclass(frozen=True)
class Issue:
    severity: str  # "error" or "warning"
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.severity.upper():7} {self.where}: {self.message}"


def load_validators(root: Path) -> dict[str, Draft202012Validator]:
    schemas = {path.name.split(".")[0]: json.loads(path.read_text()) for path in (root / "schema").glob("*.schema.json")}
    registry = Registry().with_resources([(schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()])
    return {name: Draft202012Validator(schema, registry=registry) for name, schema in schemas.items() if name != "defs"}


def validate(root: Path) -> list[Issue]:
    documents, parse_errors = load_documents(root)
    issues = [Issue("error", error.split(":", 1)[0], error.split(":", 1)[1].strip()) for error in parse_errors]
    issues += _schema_and_file_checks(root, documents)
    if any(issue.severity == "error" for issue in issues):
        # Cross-references assume schema-valid documents.
        return issues
    graph = Graph.load(root)
    return issues + _Checker(graph).run()


def _schema_and_file_checks(root: Path, documents: list[Document]) -> list[Issue]:
    validators = load_validators(root)
    issues, seen = [], {}
    for doc in documents:
        rel = str(doc.path.relative_to(root))
        for error in validators[doc.schema].iter_errors(doc.data):
            location = "/".join(map(str, error.absolute_path)) or "(top level)"
            issues.append(Issue("error", rel, f"schema: {location}: {error.message[:300]}"))
        node_id = doc.data.get("id")
        if node_id != doc.path.stem:
            issues.append(Issue("error", rel, f"id {node_id!r} does not match the file name"))
        if doc.schema == "thing":
            expected = THING_DIRS.get(doc.path.parent.name)
            if doc.data.get("kind") != expected:
                issues.append(Issue("error", rel, f"kind {doc.data.get('kind')!r} does not belong in {doc.path.parent.name}/"))
        if doc.schema != "quantity":
            # Ids are unique across all node types so that requirements can refer to them unambiguously.
            if node_id in seen:
                issues.append(Issue("error", rel, f"duplicate id {node_id!r} (also in {seen[node_id]})"))
            seen[node_id] = rel
    return issues


class _Checker:
    def __init__(self, graph: Graph) -> None:
        self.g = graph
        self.issues: list[Issue] = []

    def error(self, where: str, message: str) -> None:
        self.issues.append(Issue("error", where, message))

    def warn(self, where: str, message: str) -> None:
        self.issues.append(Issue("warning", where, message))

    def run(self) -> list[Issue]:
        for thing_id, thing in self.g.things.items():
            self.check_thing(thing_id, thing)
        for route_id, route in self.g.routes.items():
            self.check_route(route_id, route)
        for profile_id, profile in self.g.profiles.items():
            self.check_profile(profile_id, profile)
        for job_id, job in self.g.jobs.items():
            self.check_job(job_id, job)
        self.check_gaps()
        return self.issues

    # ------------------------------------------------------------------ helpers

    def check_range(self, where: str, value) -> None:
        if isinstance(value, list) and value[0] > value[1]:
            self.error(where, f"range {value} has low > high")

    def check_quantities(self, where: str, quantities: dict | None) -> None:
        for quantity, value in (quantities or {}).items():
            if quantity not in self.g.quantities:
                self.error(where, f"unknown quantity {quantity!r}")
            self.check_range(f"{where}.{quantity}", value)

    def check_band(self, where: str, quantity: str, band_id: str) -> None:
        if band_id not in {band["id"] for band in self.g.bands(quantity)}:
            self.error(where, f"unknown {quantity} band {band_id!r}")

    def check_target(self, where: str, target: str) -> None:
        if target not in self.g.things:
            self.error(where, f"unknown target {target!r}")

    # ------------------------------------------------------------------ per type

    def check_thing(self, thing_id: str, thing: dict) -> None:
        where = f"thing {thing_id}"
        for category in thing.get("is_a", []):
            if self.g.kind(category) != "category":
                self.error(where, f"is_a {category!r} is not a category")
        self.check_quantities(where, thing.get("quantities"))
        for quantity in thing.get("dimensions", []):
            if quantity not in self.g.quantities:
                self.error(where, f"unknown dimension {quantity!r}")

    def check_route(self, route_id: str, route: dict) -> None:
        where = f"route {route_id}"
        kind, target = achieved_kind(route), achieved_id(route)
        expected = {"thing": ("material", "artifact"), "effect": ("effect",), "verb": ("verb",)}[kind]
        if self.g.kind(target) not in expected:
            self.error(where, f"achieves {kind} {target!r}, which is not a known {' or '.join(expected)}")
        if kind == "thing" and target not in [output["thing"] for output in route.get("outputs", [])]:
            self.error(where, f"achieves {target!r} but does not list it in outputs")
        if kind != "effect" and "provides" in route:
            self.error(where, "only effect routes may use provides")
        if kind != "verb" and "applies_to" in route:
            self.error(where, "only verb routes may use applies_to")
        if kind == "effect" and self.g.kind(target) == "effect":
            dimensions = set(self.g.things[target]["dimensions"])
            for quantity in route.get("provides", {}):
                if quantity not in dimensions:
                    self.error(where, f"provides {quantity!r}, which is not a dimension of {target!r}")
        self.check_quantities(f"{where}.provides", route.get("provides"))
        for technique in route.get("techniques", []):
            if self.g.kind(technique) not in ("technique", "knowledge"):
                self.error(where, f"techniques lists {technique!r}, which is not a technique or knowledge")
        for item in route.get("applies_to", []):
            if item not in self.g.things:
                self.error(where, f"applies_to lists unknown {item!r}")
        for index, requirement in enumerate(route["requires"]):
            self.check_requirement(f"{where}.requires[{index}]", requirement, is_verb_route=kind == "verb")
        for output in route.get("outputs", []):
            if self.g.kind(output["thing"]) not in ("material", "artifact"):
                self.error(where, f"output {output['thing']!r} is not a known material or artifact")
            self.check_quantities(f"{where}.outputs", output.get("quantities"))
        self.check_envelope(where, route.get("envelope", {}))

    def check_requirement(self, where: str, requirement: dict, is_verb_route: bool) -> None:
        role = requirement["role"]
        if "thing" in requirement:
            kind = self.g.kind(requirement["thing"])
            if kind not in HELD_KINDS:
                self.error(where, f"{role} must point at a material, artifact or source, not {kind or 'unknown id'} {requirement['thing']!r}")
        if "category" in requirement and self.g.kind(requirement["category"]) != "category":
            self.error(where, f"unknown category {requirement['category']!r}")
        if "effect" in requirement and self.g.kind(requirement["effect"]) != "effect":
            self.error(where, f"unknown effect {requirement['effect']!r}")
        if role == "action":
            if requirement["verb"] not in self.g.verbs:
                self.error(where, f"unknown verb {requirement['verb']!r}")
            self.check_target(where, requirement["target"])
        for condition in requirement.get("where", []):
            quantity = condition["quantity"]
            if quantity not in self.g.quantities:
                self.error(where, f"unknown quantity {quantity!r}")
            if "band" in condition:
                self.check_band(where, quantity, condition["band"])
            value = condition.get("value")
            if isinstance(value, str):
                if not is_verb_route:
                    self.error(where, "target.* conditions are only allowed in verb routes")
                if value.split(".", 1)[1] not in self.g.quantities:
                    self.error(where, f"unknown target quantity in {value!r}")

    def check_envelope(self, where: str, envelope: dict) -> None:
        rate = envelope.get("rate")
        if rate:
            if rate["quantity"] not in self.g.quantities:
                self.error(where, f"unknown rate quantity {rate['quantity']!r}")
            for entry in rate.get("by_target", []):
                self.check_target(f"{where}.rate", entry["target"])
                self.check_range(f"{where}.rate.{entry['target']}", entry["value"])
        for band_id in envelope.get("precision", {}).get("bands", []):
            self.check_band(f"{where}.precision", "tolerance_mm", band_id)
        capacity = envelope.get("capacity")
        if capacity and capacity["quantity"] not in self.g.quantities:
            self.error(where, f"unknown capacity quantity {capacity['quantity']!r}")

    def check_profile(self, profile_id: str, profile: dict) -> None:
        where = f"profile {profile_id}"
        for item in profile["includes"]:
            if "id" in item:
                if self.g.kind(item["id"]) not in HELD_KINDS:
                    self.error(where, f"includes {item['id']!r}, which is not a known material, artifact or source")
            else:
                if item["verb"] not in self.g.verbs:
                    self.error(where, f"unknown verb {item['verb']!r}")
                self.check_target(where, item["target"])

    def check_job(self, job_id: str, job: dict) -> None:
        where = f"job {job_id}"
        steps = job.get("steps") or [job]
        for index, step in enumerate(steps):
            step_where = f"{where}.steps[{index}]" if "steps" in job else where
            if step["verb"] not in self.g.verbs:
                self.error(step_where, f"unknown verb {step['verb']!r}")
            self.check_target(step_where, step["target"])
            self.check_quantities(step_where, step["parameters"])
            if "precision" in step.get("limits", {}):
                self.check_band(step_where, "tolerance_mm", step["limits"]["precision"])
        if "precision" in job.get("limits", {}):
            self.check_band(where, "tolerance_mm", job["limits"]["precision"])

    # ------------------------------------------------------------------ evidence gaps (warnings)

    def check_gaps(self) -> None:
        outputs = {output["thing"] for route in self.g.routes.values() for output in route.get("outputs", [])}
        used_techniques = {technique for route in self.g.routes.values() for technique in route.get("techniques", [])}
        for thing_id, thing in self.g.things.items():
            needs_route = thing["kind"] == "artifact" or (thing["kind"] == "material" and thing.get("origin") in ("produced", "extracted"))
            if needs_route and thing_id not in outputs and thing.get("era") != "modern":
                self.warn(f"thing {thing_id}", "no route produces it")
            if thing["kind"] == "material" and thing.get("origin") == "natural" and thing.get("availability") == "regional":
                self.warn(f"thing {thing_id}", "regional natural material: give it a source and an extraction route (ADR 0032)")
            if thing["kind"] == "source" and not any(source_used(route, thing_id) for route in self.g.routes.values()):
                self.warn(f"thing {thing_id}", "no route extracts anything from this source")
            if thing["kind"] == "category" and not self.g.members(thing_id):
                self.warn(f"thing {thing_id}", "category has no members")
            if thing["kind"] in ("technique", "knowledge") and thing_id not in used_techniques:
                self.warn(f"thing {thing_id}", "no route uses this technique")
        for route_id, route in self.g.routes.items():
            if all(reference["status"] == "unverified" for reference in route["references"]):
                self.warn(f"route {route_id}", "only unverified references")


def source_used(route: dict, source: str) -> bool:
    return any(requirement.get("thing") == source for requirement in route["requires"])
