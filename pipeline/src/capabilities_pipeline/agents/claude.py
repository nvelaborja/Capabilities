"""Asking Claude Code for one structured answer, on the user's Claude login (ADR 0048).

Each call is a fresh `claude -p` process: no saved session, no CLAUDE.md, plugins, hooks or MCP servers (`--safe-mode`,
`--strict-mcp-config`), only the tools the role needs, a turn limit, and a JSON Schema the answer must match. The
stream of events it prints gives the tools it used (the searches and pages fetched, for the audit log), its token
usage, and how much of the plan's five-hour and weekly limits are used, which is how a run knows when to stop.

An API key would take precedence over the login and bill the API, so a run refuses to start with one set.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field

# Environment variables that would make Claude Code use something other than the user's Claude login.
API_CREDENTIALS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX")
# How Claude Code says a plan's limit is used up, when it says it in words rather than in a rate-limit event.
LIMIT_REACHED = re.compile(r"usage limit|limit reached|hit your limit|rate limit", re.IGNORECASE)
TIMEOUT_S = 900


class AgentError(Exception):
    """A call gave no usable answer: it failed, ran out of turns, or returned no structured output."""


class UsageLimitReached(AgentError):
    """The plan's usage limit is reached: nothing more can be asked until it resets."""


class NotOnClaudeLogin(Exception):
    """Claude Code would not run on the user's Claude subscription, so a run would be billed elsewhere, or not run."""


@dataclass(frozen=True)
class Answer:
    output: dict
    tool_calls: list[dict]  # each tool the agent used, with its input (a search's query, a fetch's URL)
    usage: dict
    cost_usd: float | None  # what the same tokens would cost on the API; the plan doesn't charge it
    limits: dict[str, float]  # how much of each window of the plan's usage is used, 0 to 1: five_hour, seven_day
    session_id: str | None
    num_turns: int | None
    duration_ms: int | None
    events: list[dict] = field(repr=False, default_factory=list)  # everything the call printed, for the audit log


@dataclass(frozen=True)
class ClaudeCode:
    """One role's way of calling Claude Code: its model, the tools it may use, and how many turns it gets."""

    model: str
    tools: tuple[str, ...] = ()
    max_turns: int = 20
    command: str = "claude"
    timeout_s: int = TIMEOUT_S

    def settings(self) -> dict:
        return {"model": self.model, "tools": list(self.tools), "max_turns": self.max_turns}

    def arguments(self, system: str, schema: dict) -> list[str]:
        tools = ",".join(self.tools)
        arguments = [
            self.command, "-p",
            "--safe-mode", "--strict-mcp-config", "--no-session-persistence",
            "--model", self.model,
            "--max-turns", str(self.max_turns),
            "--tools", tools,
        ]
        if self.tools:
            # Print mode asks before using a web tool; nobody is there to answer, so they are allowed up front.
            arguments += ["--allowedTools", tools]
        return arguments + [
            "--permission-prompts", "none",
            "--system-prompt", system,
            "--output-format", "stream-json", "--verbose",
            "--json-schema", json.dumps(schema),
        ]

    def ask(self, prompt: str, system: str, schema: dict) -> Answer:
        """One answer matching `schema`. The prompt goes in on stdin: it can be long, and no option can swallow it."""
        refuse_api_credentials()
        # An empty working directory: nothing in it for the agent to read, and no project settings to pick up.
        with tempfile.TemporaryDirectory(prefix="agent-") as cwd:
            try:
                completed = subprocess.run(
                    self.arguments(system, schema), input=prompt, capture_output=True, text=True, cwd=cwd,
                    env=os.environ.copy(), timeout=self.timeout_s,
                )
            except subprocess.TimeoutExpired as error:
                raise AgentError(f"no answer within {self.timeout_s} s") from error
            except OSError as error:
                raise AgentError(f"couldn't run {self.command}: {error}") from error
        return parse(completed.stdout, completed.stderr, completed.returncode)


def parse(stdout: str, stderr: str = "", returncode: int = 0) -> Answer:
    """Read what `claude -p --output-format stream-json --verbose` printed: one JSON event per line, the last a result."""
    events = []
    for line in stdout.splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a stray line of text isn't an event
    limits, limited = {}, False
    tool_calls = []
    for event in events:
        if event.get("type") == "rate_limit_event":
            info = event.get("rate_limit_info") or {}
            for window, state in (info.get("unifiedWindows") or {}).items():
                limits[window] = state.get("utilization")
                limited = limited or state.get("status") not in (None, "allowed")
            limited = limited or info.get("status") not in (None, "allowed")
        elif event.get("type") == "assistant":
            for block in (event.get("message") or {}).get("content") or []:
                if block.get("type") in ("tool_use", "server_tool_use") and block.get("name") != "StructuredOutput":
                    tool_calls.append({"name": block.get("name"), "input": block.get("input")})
    result = next((event for event in reversed(events) if event.get("type") == "result"), None)
    if result is None:
        message = (stderr or stdout).strip()[-500:]
        if limited or LIMIT_REACHED.search(message):
            raise UsageLimitReached(message or "the plan's usage limit is reached")
        raise AgentError(f"Claude Code exited with {returncode} and no result: {message or 'no output'}")
    if result.get("is_error") or result.get("subtype") != "success":
        message = str(result.get("result") or result.get("subtype"))
        if limited or result.get("api_error_status") == 429 or LIMIT_REACHED.search(message):
            raise UsageLimitReached(message)
        if result.get("subtype") == "error_max_turns":
            raise AgentError(f"ran out of turns ({result.get('num_turns')}) before answering")
        raise AgentError(f"Claude Code failed: {message[:500]}")
    if not isinstance(result.get("structured_output"), dict):
        raise AgentError("the answer had no structured output")
    return Answer(
        output=result["structured_output"],
        tool_calls=tool_calls,
        usage=result.get("usage") or {},
        cost_usd=result.get("total_cost_usd"),
        limits=limits,
        session_id=result.get("session_id"),
        num_turns=result.get("num_turns"),
        duration_ms=result.get("duration_ms"),
        events=events,
    )


def refuse_api_credentials() -> None:
    if found := [name for name in API_CREDENTIALS if os.environ.get(name)]:
        raise NotOnClaudeLogin(
            f"{', '.join(found)} is set: Claude Code would use it instead of your Claude login, and the run would be "
            "billed to it. Unset it and run again."
        )


def check_login(command: str = "claude") -> dict:
    """That Claude Code is logged in to a Claude subscription (not an API key or a cloud provider), and which plan. Only
    those two facts are kept: the status also names the account, which the audit log has no need of."""
    refuse_api_credentials()
    try:
        completed = subprocess.run([command, "auth", "status"], capture_output=True, text=True, timeout=60)
        status = json.loads(completed.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        raise NotOnClaudeLogin(f"couldn't read `{command} auth status`: {error}") from error
    if not status.get("loggedIn"):
        raise NotOnClaudeLogin(f"Claude Code isn't logged in. Run `{command}` and log in with your Claude account.")
    if status.get("authMethod") != "claude.ai":
        raise NotOnClaudeLogin(
            f"Claude Code is using {status.get('authMethod')!r}, not a Claude login, so the run would be billed to it. "
            f"Run `{command}` and log in with your Claude account (/login)."
        )
    return {"auth": status.get("authMethod"), "plan": status.get("subscriptionType")}
