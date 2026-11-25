"""The audit log of agent runs: an append-only DuckDB file in audit/, kept out of git (ADR 0035, ADR 0048).

Every call to an agent, every mechanical check and every outcome is a new row; nothing is updated or deleted. A run's
start and its end are separate rows for the same reason. From any fact the run that proposed it can be found
(`proposed_by` in the crosswalk), and from any run, prompt version or model, every proposal it made.

Each pull request also carries a summary of its run (data/agent_runs/<run>.json), so the record of what was merged
doesn't depend on this file surviving.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from .claude import Answer

AUDIT_DIR = "audit"
AUDIT_FILE = "agents.duckdb"

TABLES = {
    "run_starts": "run_id varchar, task varchar, mode varchar, settings json, login json, git_commit varchar, recorded_at timestamptz",
    "run_ends": "run_id varchar, stopped_because varchar, outcomes json, pull_request varchar, usage json, recorded_at timestamptz",
    "calls": "run_id varchar, item varchar, attempt integer, role varchar, prompt_version varchar, settings json, "
             "prompt varchar, output json, tool_calls json, usage json, cost_usd double, limits json, "
             "session_id varchar, num_turns integer, duration_ms bigint, error varchar, events json, recorded_at timestamptz",
    "checks": "run_id varchar, item varchar, attempt integer, name varchar, passed boolean, detail varchar, "
              "recorded_at timestamptz",
    "outcomes": "run_id varchar, item varchar, outcome varchar, reason varchar, row json, recorded_at timestamptz",
}


def audit_dir_for(root: Path) -> Path:
    """Where the audit log and run summaries go: $CAPABILITIES_AUDIT_DIR, else audit/ in the repository."""
    env = os.environ.get("CAPABILITIES_AUDIT_DIR")
    return Path(env).resolve() if env else root / AUDIT_DIR


class AuditLog:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.connection = duckdb.connect(str(path))
        for table, columns in TABLES.items():
            self.connection.execute(f"create table if not exists {table} ({columns})")

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> AuditLog:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def run_started(self, run_id: str, task: str, mode: str, settings: dict, login: dict, git_commit: str | None):
        self._insert("run_starts", run_id, task, mode, _json(settings), _json(login), git_commit)

    def run_ended(self, run_id: str, stopped_because: str | None, outcomes: dict, pull_request: str | None, usage: dict):
        self._insert("run_ends", run_id, stopped_because, _json(outcomes), pull_request, _json(usage))

    def call(self, run_id: str, item: str, attempt: int, role: str, prompt_version: str, settings: dict, prompt: str,
             answer: Answer | None = None, error: str | None = None):
        self._insert(
            "calls", run_id, item, attempt, role, prompt_version, _json(settings), prompt,
            _json(answer.output) if answer else None,
            _json(answer.tool_calls) if answer else None,
            _json(answer.usage) if answer else None,
            answer.cost_usd if answer else None,
            _json(answer.limits) if answer else None,
            answer.session_id if answer else None,
            answer.num_turns if answer else None,
            answer.duration_ms if answer else None,
            error,
            _json(answer.events) if answer else None,
        )

    def check(self, run_id: str, item: str, attempt: int, name: str, passed: bool, detail: str):
        self._insert("checks", run_id, item, attempt, name, passed, detail)

    def outcome(self, run_id: str, item: str, outcome: str, reason: str, row: dict | None):
        self._insert("outcomes", run_id, item, outcome, reason, _json(row) if row else None)

    def _insert(self, table: str, *values):
        placeholders = ", ".join("?" for _ in range(len(values) + 1))
        self.connection.execute(f"insert into {table} values ({placeholders})", [*values, _now()])


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _now() -> datetime:
    return datetime.now(timezone.utc)
